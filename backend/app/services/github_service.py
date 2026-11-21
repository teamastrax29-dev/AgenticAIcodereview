import httpx
from fastapi import HTTPException
from app.config import settings
from urllib.parse import quote

GITHUB_API = "https://api.github.com"

async def get_file_content(
    token: str,
    full_name: str,
    file_path: str,
    ref: str,
) -> str | None:
    """Downloads raw UTF-8 text of a single file at a branch or commit SHA."""
    encoded_path = quote(file_path, safe="/")
    headers = {
        **_headers(token),
        "Accept": "application/vnd.github.raw+json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{full_name}/contents/{encoded_path}",
            headers=headers,
            params={"ref": ref},
        )
        if resp.status_code != 200:
            return None

        # Skip oversized files (> 250 KB) or binary content
        if len(resp.content) > 250_000 or b"\x00" in resp.content:
            return None

        return resp.content.decode("utf-8", errors="ignore")


async def get_pr_files_content(
    token: str,
    full_name: str,
    pr_number: int,
) -> list[dict[str, str]]:
    """
    Reuses get_pr_with_diff() to get the PR head commit and changed files,
    then downloads full file contents at head_sha for Semgrep scanning.
    """
    pr_data = await get_pr_with_diff(token, full_name, pr_number)
    head_sha = pr_data["head_sha"]

    results: list[dict[str, str]] = []
    for f in pr_data["files"]:
        if f["status"] == "removed":
            continue

        content = await get_file_content(token, full_name, f["filename"], head_sha)
        if content:
            results.append({"path": f["filename"], "content": content})

    return results
    
def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_CALLBACK_URL,
            },
        )
        data = resp.json()
        if "access_token" not in data:
            raise HTTPException(status_code=400, detail=data.get("error_description", "GitHub OAuth failed"))
        return data["access_token"]


async def get_github_user(token: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GITHUB_API}/user", headers=_headers(token))
        resp.raise_for_status()
        return resp.json()


async def list_user_repos(token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_headers(token),
            params={"sort": "updated", "per_page": 30},
        )
        resp.raise_for_status()
        return [
            {
                "github_repo_id": r["id"],
                "full_name": r["full_name"],
                "default_branch": r["default_branch"],
                "private": r["private"],
            }
            for r in resp.json()
        ]


async def get_repo_tree(token: str, full_name: str, branch: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{full_name}/git/trees/{branch}",
            headers=_headers(token),
            params={"recursive": "1"},
        )
        resp.raise_for_status()
        tree = resp.json().get("tree", [])
        return [
            {"path": item["path"], "sha": item["sha"], "size": item.get("size", 0)}
            for item in tree
            if item.get("type") == "blob"
        ]


async def list_open_pulls(token: str, full_name: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{full_name}/pulls",
            headers=_headers(token),
            params={"state": "open", "per_page": 20},
        )
        resp.raise_for_status()
        return [
            {
                "pr_number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "head_sha": pr["head"]["sha"],
            }
            for pr in resp.json()
        ]


async def get_pr_with_diff(token: str, full_name: str, pr_number: int) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        pr_resp = await client.get(f"{GITHUB_API}/repos/{full_name}/pulls/{pr_number}", headers=_headers(token))
        if pr_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Pull request not found")
        pr_resp.raise_for_status()
        pr = pr_resp.json()

        files_resp = await client.get(
            f"{GITHUB_API}/repos/{full_name}/pulls/{pr_number}/files",
            headers=_headers(token),
            params={"per_page": 100},
        )
        files_resp.raise_for_status()

        files = [
            {
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
                "patch": f.get("patch", ""),
            }
            for f in files_resp.json()
        ]
        return {
            "pr_number": pr["number"],
            "title": pr["title"],
            "head_sha": pr["head"]["sha"],
            "files": files,
        }