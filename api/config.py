"""
config.py — API 설정 및 경로/경로주입.

uvicorn 을 repo root 또는 api/ 어디서 실행하든 `from core.pipeline import run_pipeline`
가 동작하도록 src/ 를 sys.path 에 주입한다. (src/core/* 가 아직 없어도 import 자체는
지연 import 로 처리하므로 앱 기동에는 영향 없음.)
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── repo 루트 탐색 + src/ 경로 주입 ──────────────────────────────
# api/config.py → parent=api/ → parent.parent=repo root
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SRC_ROOT: Path = REPO_ROOT / "src"

# src/ 를 우선순위로 sys.path 에 주입 → `from core.pipeline import ...` 가능
_src_str = str(SRC_ROOT)
if _src_str not in sys.path:
    sys.path.insert(0, _src_str)

# ── 결과/데이터 디렉토리 ─────────────────────────────────────────
RESULT_ROOT: Path = REPO_ROOT / "results" / "api"
DATA_ROOT: Path = REPO_ROOT / "data"
UPLOAD_ROOT: Path = RESULT_ROOT / "_uploads"

# 디렉토리 보장 (없으면 생성)
RESULT_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# ── CORS ─────────────────────────────────────────────────────────
# Next.js 개발 서버 (web/) 는 :3000 에서 동작.
CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def result_dir_for(session_id: str) -> Path:
    """세션별 결과 디렉토리 경로 (없으면 생성)."""
    d = RESULT_ROOT / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d
