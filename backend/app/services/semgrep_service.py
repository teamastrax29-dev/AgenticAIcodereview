import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def run_semgrep_scan(files: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Writes PR files into a sandboxed temp folder, runs Semgrep CLI with p/default,
    and returns normalized static analysis findings.
    files: list of {"path": "app/auth.py", "content": "..."}
    """
    if not files:
        return []

    with tempfile.TemporaryDirectory(prefix="semgrep_scan_") as tmp_dir:
        base_path = Path(tmp_dir)

        for file_item in files:
            rel_path = Path(file_item["path"].lstrip("/"))
            target_path = (base_path / rel_path).resolve()

            # Prevent path-traversal attacks
            if not str(target_path).startswith(str(base_path.resolve())):
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(file_item["content"], encoding="utf-8", errors="ignore")

        process = await asyncio.create_subprocess_exec(
            "semgrep",
            "scan",
            "--config", "p/default",
            "--json",
            "--quiet",
            "--metrics=off",
            "--no-git-ignore",
            str(base_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

        if not stdout:
            if stderr:
                logger.error("Semgrep failed (code %s): %s", process.returncode, stderr.decode("utf-8", errors="ignore"))
            return []

        raw_output = json.loads(stdout.decode("utf-8"))

        findings: List[Dict[str, Any]] = []
        for item in raw_output.get("results", []):
            abs_file = Path(item.get("path", ""))
            try:
                clean_path = str(abs_file.relative_to(base_path)).replace("\\", "/")
            except ValueError:
                clean_path = str(abs_file)

            extra = item.get("extra", {})
            findings.append({
                "file_path": clean_path,
                "start_line": item.get("start", {}).get("line"),
                "end_line": item.get("end", {}).get("line"),
                "rule_id": item.get("check_id"),
                "severity": extra.get("severity", "WARNING"),
                "message": extra.get("message", ""),
                "code_snippet": extra.get("lines", "").strip(),
            })

        return findings