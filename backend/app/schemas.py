import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    id: uuid.UUID
    github_id: int
    username: str
    avatar_url: str | None = None
    model_config = ConfigDict(from_attributes=True)


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RepoConnectIn(BaseModel):
    github_repo_id: int
    full_name: str
    default_branch: str = "main"


class RepoOut(BaseModel):
    id: uuid.UUID
    github_repo_id: int
    full_name: str
    default_branch: str
    index_status: str
    last_indexed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ReviewCreateIn(BaseModel):
    repo_id: uuid.UUID
    pr_number: int


class ReviewCommentOut(BaseModel):
    id: uuid.UUID
    file_path: str
    line_number: int
    severity: str
    issue: str
    suggested_patch: str | None = None
    rag_source: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ReviewOut(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    pr_number: int
    pr_title: str
    commit_sha: str
    status: str
    files_changed: int
    created_at: datetime
    comments: list[ReviewCommentOut] = []
    model_config = ConfigDict(from_attributes=True)