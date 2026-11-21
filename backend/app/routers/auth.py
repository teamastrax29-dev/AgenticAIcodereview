from urllib.parse import urlencode
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import AuthTokenOut, UserOut
from app.security import create_access_token, encrypt_token, get_current_user
from app.services.github_service import exchange_code_for_token, get_github_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/github/login")
async def github_login():
    params = urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_CALLBACK_URL,
        "scope": "repo read:user",
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback", response_model=AuthTokenOut)
async def github_callback(code: str, db: AsyncSession = Depends(get_db)):
    gh_token = await exchange_code_for_token(code)
    gh_user = await get_github_user(gh_token)

    result = await db.execute(select(User).where(User.github_id == gh_user["id"]))
    user = result.scalar_one_or_none()

    if user:
        user.username = gh_user["login"]
        user.avatar_url = gh_user.get("avatar_url")
        user.encrypted_github_token = encrypt_token(gh_token)
    else:
        user = User(
            github_id=gh_user["id"],
            username=gh_user["login"],
            avatar_url=gh_user.get("avatar_url"),
            encrypted_github_token=encrypt_token(gh_token),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    return AuthTokenOut(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user