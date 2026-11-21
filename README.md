# Agentic AI Code Review System

An automated, agentic code review platform powered by FastAPI, PostgreSQL (with `pgvector`), Semgrep static analysis, RAG code embeddings, and multi-model LLM review workflows.

---

## Architecture Overview

```
backend/
├── Dockerfile                  # Container definition for FastAPI backend
├── docker-compose.yml          # Multi-container orchestration (API + pgvector PostgreSQL)
├── requirements.txt            # Python dependencies (FastAPI, SQLAlchemy, pgvector, etc.)
├── .env.example                # Template environment variables
└── app/
    ├── main.py                 # FastAPI application factory & lifespan
    ├── config.py               # Pydantic settings management
    ├── database.py             # Async SQLAlchemy engine & session lifecycle
    ├── security.py             # JWT auth & Fernet token encryption
    ├── models.py               # SQLAlchemy ORM models (Users, Repos, Reviews, CodeChunks)
    ├── schemas.py              # Pydantic schemas for request/response serialization
    ├── services/
    │   ├── github_service.py   # GitHub REST API client (OAuth, PRs, diffs)
    │   ├── rag_service.py      # Code chunking & vector search with fastembed
    │   └── semgrep_service.py  # Static AST analysis with Semgrep
    └── routers/
        ├── auth.py             # GitHub OAuth callback & token issuance
        ├── repos.py            # Tracked repository management & GitHub sync
        ├── reviews.py          # Triggering & querying PR reviews
        └── analysis.py         # Static analysis & RAG endpoints
```

---

## Getting Started

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+ / Python 3.12
- GitHub OAuth App (Client ID & Secret)

### 2. Configure Environment Variables
Copy `.env.example` in `backend/` to `.env`:
```bash
cp backend/.env.example backend/.env
```
Fill in your credentials:
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `JWT_SECRET_KEY` (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `TOKEN_ENCRYPTION_KEY` (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)

---

## Running with Docker Compose

To start both PostgreSQL (`pgvector/pgvector:pg17`) and the FastAPI backend:

```bash
cd backend
docker compose up -d --build
```

The API will be available at:
- **API**: [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Local Development (Without Docker API container)

1. **Start only the Database container**:
   ```bash
   cd backend
   docker compose up -d db
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Run the FastAPI server**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
