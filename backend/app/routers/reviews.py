import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import Repository, ReviewRun, User
from app.schemas import ReviewCreateIn, ReviewOut
from app.security import decrypt_token, get_current_user
from app.services import github_service

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
async def create_review(
    payload: ReviewCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo_res = await db.execute(
        select(Repository).where(Repository.id == payload.repo_id, Repository.user_id == current_user.id)
    )
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    token = decrypt_token(current_user.encrypted_github_token)
    pr_data = await github_service.get_pr_with_diff(token, repo.full_name, payload.pr_number)

    review = ReviewRun(
        repo_id=repo.id,
        pr_number=pr_data["pr_number"],
        pr_title=pr_data["title"],
        commit_sha=pr_data["head_sha"],
        status="pending",
        files_changed=len(pr_data["files"]),
        raw_diff_json=pr_data["files"],
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    return ReviewOut(
        id=review.id,
        repo_id=review.repo_id,
        pr_number=review.pr_number,
        pr_title=review.pr_title,
        commit_sha=review.commit_sha,
        status=review.status,
        files_changed=review.files_changed,
        created_at=review.created_at,
        comments=[],
    )


@router.get("/{review_id}", response_model=ReviewOut)
async def get_review(
    review_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReviewRun)
        .join(Repository)
        .options(selectinload(ReviewRun.comments))
        .where(ReviewRun.id == review_id, Repository.user_id == current_user.id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review