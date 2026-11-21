import uuid
from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from pgvector.sqlalchemy import Vector


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    encrypted_github_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repositories: Mapped[list["Repository"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "github_repo_id", name="uq_user_github_repo"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    index_status: Mapped[str] = mapped_column(String(50), default="not_indexed")
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped["User"] = relationship(back_populates="repositories")
    chunks: Mapped[list["CodeChunk"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    reviews: Mapped[list["ReviewRun"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class CodeChunk(Base):
    """RAG vector table populated in Phase 2."""
    __tablename__ = "code_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("repositories.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(255))
    file_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repository: Mapped["Repository"] = relationship(back_populates="chunks")


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("repositories.id"), index=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str] = mapped_column(String(500), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    files_changed: Mapped[int] = mapped_column(Integer, default=0)
    raw_diff_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repository: Mapped["Repository"] = relationship(back_populates="reviews")
    comments: Mapped[list["ReviewComment"]] = relationship(back_populates="review", cascade="all, delete-orphan")


class ReviewComment(Base):
    """Populated by the 3-model Agentic AI pipeline in Phase 3."""
    __tablename__ = "review_comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("review_runs.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_patch: Mapped[str | None] = mapped_column(Text)
    rag_source: Mapped[str | None] = mapped_column(String(500))

    review: Mapped["ReviewRun"] = relationship(back_populates="comments")