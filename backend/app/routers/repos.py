import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Repository, User
from app.schemas import RepoConnectIn, RepoOut
from app.security import decrypt_token, get_current_user
from app.services import github_service

router = APIRouter(prefix="/api/v1/repos", tags=["repos"])


async def _get_owned_repo(repo_id: uuid.UUID, user: User, db: AsyncSession) -> Repository:
    result = await db.execute(
        select(Repository).where(Repository.id == repo_id, Repository.user_id == user.id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.get("")
async def list_github_repos(current_user: User = Depends(get_current_user)):
    token = decrypt_token(current_user.encrypted_github_token)
    return await github_service.list_user_repos(token)


@router.post("/connect", response_model=RepoOut, status_code=status.HTTP_201_CREATED)
async def connect_repo(
    payload: RepoConnectIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository).where(
            Repository.user_id == current_user.id,
            Repository.github_repo_id == payload.github_repo_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    repo = Repository(
        user_id=current_user.id,
        github_repo_id=payload.github_repo_id,
        full_name=payload.full_name,
        default_branch=payload.default_branch,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


@router.get("/{repo_id}/tree")
async def get_repository_tree(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await _get_owned_repo(repo_id, current_user, db)
    token = decrypt_token(current_user.encrypted_github_token)
    files = await github_service.get_repo_tree(token, repo.full_name, repo.default_branch)
    return {"repo_id": str(repo.id), "branch": repo.default_branch, "total_files": len(files), "files": files}


@router.get("/{repo_id}/pulls")
async def list_repo_pulls(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await _get_owned_repo(repo_id, current_user, db)
    token = decrypt_token(current_user.encrypted_github_token)
    return await github_service.list_open_pulls(token, repo.full_name)


@router.get("/{repo_id}/pulls/{pr_number}/diff")
async def get_pull_diff(
    repo_id: uuid.UUID,
    pr_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await _get_owned_repo(repo_id, current_user, db)
    token = decrypt_token(current_user.encrypted_github_token)
    return await github_service.get_pr_with_diff(token, repo.full_name, pr_number)