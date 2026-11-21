import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID

from fastembed import TextEmbedding
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CodeChunk, Repository

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".php",
    ".sql", ".yml", ".yaml", ".json", ".md",
}

IGNORED_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"
}

_embedding_model: TextEmbedding | None = None


def get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        # 768-dimensional model to match CodeChunk.embedding = Vector(768)
        _embedding_model = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")
    return _embedding_model


def is_indexable_file(file_path: str) -> bool:
    path = Path(file_path)
    if any(part in IGNORED_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def chunk_code(
    file_path: str,
    content: str,
    file_sha: str,
    chunk_size: int = 60,
    overlap: int = 10,
) -> List[Dict[str, Any]]:
    lines = content.splitlines()
    if not lines:
        return []

    chunks: List[Dict[str, Any]] = []
    step = max(1, chunk_size - overlap)

    for start in range(0, len(lines), step):
        end = min(start + chunk_size, len(lines))
        snippet = "\n".join(lines[start:end]).strip()
        if not snippet:
            continue

        chunks.append({
            "file_path": file_path,
            "symbol_name": f"lines {start + 1}-{end}",
            "file_sha": file_sha,
            "content": snippet,
        })

        if end == len(lines):
            break

    return chunks


async def embed_texts(texts: List[str]) -> List[List[float]]:
    model = get_embedding_model()

    def _compute() -> List[List[float]]:
        return [vec.tolist() for vec in model.embed(texts)]

    return await asyncio.to_thread(_compute)


async def index_repository_files(
    db: AsyncSession,
    repo: Repository,
    files: List[Dict[str, str]],
) -> int:
    """
    files: list of {"path": "src/app.py", "content": "...", "sha": "..."}
    """
    all_chunks: List[Dict[str, Any]] = []
    for f in files:
        if not is_indexable_file(f["path"]):
            continue
        sha = f.get("sha") or hashlib.sha256(f["content"].encode("utf-8")).hexdigest()[:40]
        all_chunks.extend(chunk_code(f["path"], f["content"], sha))

    await db.execute(delete(CodeChunk).where(CodeChunk.repo_id == repo.id))

    if not all_chunks:
        repo.index_status = "indexed"
        await db.commit()
        return 0

    texts_to_embed = [
        f"File: {c['file_path']} ({c['symbol_name']})\n{c['content']}"
        for c in all_chunks
    ]
    vectors = await embed_texts(texts_to_embed)

    db_objects = [
        CodeChunk(
            repo_id=repo.id,
            file_path=chunk["file_path"],
            symbol_name=chunk["symbol_name"],
            file_sha=chunk["file_sha"],
            content=chunk["content"],
            embedding=vector,
        )
        for chunk, vector in zip(all_chunks, vectors)
    ]

    db.add_all(db_objects)
    repo.index_status = "indexed"
    await db.commit()
    return len(db_objects)


async def search_similar_code(
    db: AsyncSession,
    repo_id: UUID,
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    query_vector = (await embed_texts([query]))[0]

    distance_col = CodeChunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(CodeChunk, distance_col)
        .where(CodeChunk.repo_id == repo_id)
        .order_by(distance_col)
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()

    return [
        {
            "file_path": chunk.file_path,
            "symbol_name": chunk.symbol_name,
            "file_sha": chunk.file_sha,
            "similarity": round(1.0 - float(distance), 4),
            "content": chunk.content,
        }
        for chunk, distance in rows
    ]