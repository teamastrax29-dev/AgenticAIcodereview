from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, init_db
from app.routers import analysis, auth, repos, reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Agentic AI Code Review API", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(repos.router)
app.include_router(reviews.router)
app.include_router(analysis.router)


@app.get("/health", tags=["system"])
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    ext = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    return {
        "status": "ok",
        "database": "connected",
        "pgvector_enabled": ext.scalar_one_or_none() is not None,
    }