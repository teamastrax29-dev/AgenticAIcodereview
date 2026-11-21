from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Repository, User
from app.security import decrypt_token, get_current_user  # <-- match repos.py
from app.services.github_service import (
    get_file_content,
    get_pr_files_content,
    get_repo_tree,
)
from app.services.rag_service import (
    index_repository_files,
    is_indexable_file,
    search_similar_code,
)
from app.services.semgrep_service import run_semgrep_scan

router = APIRouter(prefix="/api/v1/analysis", tags=["Phase 2 - RAG & Semgrep"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Code snippet or natural language query")
    top_k: int = Field(default=5, ge=1, le=20)


async def _get_user_repo(
    db: AsyncSession,
    repo_id: UUID,
    user_id: UUID,
) -> Repository:
    stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == user_id,
    )
    repo = (await db.execute(stmt)).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.post("/repos/{repo_id}/index")
async def index_repository(
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await _get_user_repo(db, repo_id, current_user.id)
    token = decrypt_token(current_user.encrypted_github_token)  # <-- match repos.py

    # get_repo_tree already returns only blobs: [{"path", "sha", "size"}]
    tree_items = await get_repo_tree(token, repo.full_name, repo.default_branch)

    files_to_index = []
    for item in tree_items:
        if len(files_to_index) >= 100:
            break

        if not is_indexable_file(item["path"]) or item.get("size", 0) > 250_000:
            continue

        content = await get_file_content(
            token,
            repo.full_name,
            item["path"],
            repo.default_branch,
        )
        if content:
            files_to_index.append({
                "path": item["path"],
                "sha": item["sha"],
                "content": content,
            })

    chunks_stored = await index_repository_files(db, repo, files_to_index)

    return {
        "repo_id": str(repo.id),
        "files_indexed": len(files_to_index),
        "chunks_stored": chunks_stored,
        "index_status": repo.index_status,
    }


@router.post("/repos/{repo_id}/search")
async def semantic_search(
    repo_id: UUID,
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await _get_user_repo(db, repo_id, current_user.id)
    results = await search_similar_code(db, repo.id, payload.query, payload.top_k)

    return {
        "repo_id": str(repo.id),
        "query": payload.query,
        "total_matches": len(results),
        "matches": results,
    }


@router.post("/repos/{repo_id}/pulls/{pr_number}/semgrep")
async def scan_pull_request(
    repo_id: UUID,
    pr_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = await _get_user_repo(db, repo_id, current_user.id)
    token = decrypt_token(current_user.encrypted_github_token)  # <-- match repos.py

    pr_files = await get_pr_files_content(token, repo.full_name, pr_number)
    findings = await run_semgrep_scan(pr_files)

    return {
        "repo_id": str(repo.id),
        "pr_number": pr_number,
        "files_scanned": len(pr_files),
        "total_findings": len(findings),
        "findings": findings,
    }