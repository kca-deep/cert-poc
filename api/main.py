"""
main.py — FastAPI 앱 진입점.

실행 (repo root 에서):
    uvicorn api.main:app --reload --port 8000
또는 (api/ 에서):
    uvicorn main:app --reload --port 8000

라우터는 src/core/pipeline.py 가 아직 없어도 import 가 깨지지 않도록
각 핸들러 내부에서 지연 import 한다 (routers/* 참조).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db
from .routers import sessions, upload, llm

app = FastAPI(title="cert-poc API", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    """SQLite 스키마 생성 (멱등)."""
    db.init_db()

# ── CORS — Next.js (web/) 개발 서버 허용 ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ──────────────────────────────────────────────────
app.include_router(sessions.router)
app.include_router(upload.router)
app.include_router(llm.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """헬스 체크."""
    return {"status": "ok"}
