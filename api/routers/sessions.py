"""
sessions.py — 세션 CRUD + SSE 진행률 스트림 (DB 영속 + 실연결).

엔드포인트 (web/lib/api.ts 와 경로 일치):
    GET  /sessions                 세션 목록 (Session[])
    GET  /sessions/{id}            세션 상세 (SessionDetail) or 404
    GET  /sessions/{id}/progress   SSE 스트림 (run_pipeline 실연결)
    POST /sessions                 ParseResult 수신 → 세션 생성 + 분석 시작 → {"id"}

응답 JSON 은 web/lib/types.ts 의 인터페이스(camelCase)를 그대로 미러링한다.
SSE 이벤트 키는 src/core/events.py 의 camelCase 계약을 무변환으로 전달한다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .. import config, db, progress_hub

router = APIRouter(tags=["sessions"])


# ── Pydantic 모델 (web/lib/types.ts 미러, camelCase) ─────────────

class Session(BaseModel):
    id: str
    createdAt: str
    originalFilename: str
    fileType: Literal["hwp", "hwpx", "pdf"]
    status: Literal["uploading", "parsing", "running", "done", "error"]
    questionCount: int
    foundCount: int
    elapsedSeconds: float | None = None
    provider: Literal["local", "claude"] = "local"


class Question(BaseModel):
    qNumber: int
    mdText: str


class Issue(BaseModel):
    location: str
    original: str
    suspected: str
    suggested: str | None = None
    extra: dict[str, Any] | None = None


class AnomalyResult(BaseModel):
    qNumber: int
    typeCode: str
    layer: int
    found: bool
    confidence: str | None = None
    issues: list[Issue] = []
    filtered: bool | None = None
    filterReason: str | None = None


class SessionDetail(BaseModel):
    session: Session
    questions: list[Question] = []
    results: list[AnomalyResult] = []


class CreateSessionRequest(BaseModel):
    """프론트 startAnalysis 가 보내는 ParseResult (web/lib/types.ts)."""
    filename: str
    fileType: Literal["hwp", "hwpx", "pdf"]
    questionCount: int = 0
    questions: list[Question] = []
    mergedMd: str = ""
    provider: Literal["local", "claude"] | None = None


class CreateSessionResponse(BaseModel):
    id: str


class RerunRequest(BaseModel):
    """기존 세션을 (가능하면 다른 공급자로) 다시 분석."""
    provider: Literal["local", "claude"] | None = None


class ReviewAction(BaseModel):
    """담당자 검수 결정 (web/lib/types.ts ReviewAction 미러)."""
    qNumber: int
    typeCode: str
    action: Literal["confirmed", "rejected", "pending"]
    comment: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_provider(explicit: str | None) -> str:
    """src/config.py 의 단일 정의로 공급자를 해석한다 (기본값 일원화)."""
    from config import resolve_provider  # src/ 는 api.config import 시 sys.path 등록됨
    return resolve_provider(explicit)


# ── GET /sessions ────────────────────────────────────────────────
@router.get("/sessions")
async def list_sessions() -> list[Session]:
    return [Session(**s) for s in db.list_sessions()]


# ── GET /sessions/{id} ───────────────────────────────────────────
@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionDetail:
    detail = db.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionDetail(
        session=Session(**detail["session"]),
        questions=[Question(**q) for q in detail["questions"]],
        results=[AnomalyResult(**r) for r in detail["results"]],
    )


# ── DELETE /sessions/{id} ────────────────────────────────────────
@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, bool]:
    """세션 1건 삭제 (questions/anomaly_results/review_actions CASCADE). 없으면 404."""
    if not db.delete_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


# ── POST /sessions ───────────────────────────────────────────────
@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    """
    파싱 결과(ParseResult)를 받아 세션을 영속화하고 백그라운드 분석을 시작한다.
    md_text 는 mergedMd 를 우선 사용하고, 없으면 문항 본문을 합쳐 복원한다.
    """
    sid = uuid.uuid4().hex[:12]
    md_text = req.mergedMd or "\n\n".join(q.mdText for q in req.questions)
    provider = _resolve_provider(req.provider)

    session = {
        "id": sid,
        "createdAt": _now_iso(),
        "originalFilename": req.filename,
        "fileType": req.fileType,
        "status": "running",
        "questionCount": req.questionCount or len(req.questions),
        "foundCount": 0,
        "elapsedSeconds": 0,
        "provider": provider,
    }
    db.create_session(
        session, md_text,
        [{"qNumber": q.qNumber, "mdText": q.mdText} for q in req.questions],
    )

    # 백그라운드 분석 시작 (run_pipeline 을 별도 스레드에서 구동).
    progress_hub.start(sid, md_text, config.result_dir_for(sid), provider=provider)
    return CreateSessionResponse(id=sid)


# ── POST /sessions/{id}/rerun ────────────────────────────────────
@router.post("/sessions/{session_id}/rerun")
async def rerun_session(session_id: str, req: RerunRequest) -> CreateSessionResponse:
    """
    기존 세션을 다시 분석한다. 업로드/파싱 없이 저장된 md_text 를 재사용하며,
    LLM 서버 미가용(Connection error)으로 실패한 세션을 다른 공급자로 재시도하는
    용도다. reset=True 로 이전(에러 포함) 레이어 결과를 무시하고 재질의한다.
    """
    md_text = db.get_md_text(session_id)
    if md_text is None:
        raise HTTPException(status_code=404, detail="session not found")

    provider = _resolve_provider(req.provider) if req.provider \
        else (db.get_provider(session_id) or _resolve_provider(None))

    db.reset_for_rerun(session_id, provider)
    progress_hub.start(session_id, md_text, config.result_dir_for(session_id),
                       provider=provider, reset=True)
    return CreateSessionResponse(id=session_id)


# ── GET /sessions/{id}/reviews ───────────────────────────────────
@router.get("/sessions/{session_id}/reviews")
async def list_reviews(session_id: str) -> list[ReviewAction]:
    """세션의 검수 결정 목록 (DB 영속)."""
    if db.get_status(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [ReviewAction(**r) for r in db.list_reviews(session_id)]


# ── PUT /sessions/{id}/reviews ───────────────────────────────────
@router.put("/sessions/{session_id}/reviews")
async def upsert_review(session_id: str, req: ReviewAction) -> dict[str, bool]:
    """검수 결정 1건 저장/갱신 (확인·반려·보류)."""
    if db.get_status(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    db.upsert_review(session_id, req.qNumber, req.typeCode,
                     req.action, req.comment, _now_iso())
    return {"ok": True}


# ── GET /sessions/{id}/progress ──────────────────────────────────
@router.get("/sessions/{session_id}/progress")
async def session_progress(session_id: str) -> EventSourceResponse:
    """
    SSE 진행률 스트림. progress_hub 버퍼를 구독해 ProgressEvent(camelCase)를
    그대로 JSON 직렬화한다. 프론트(web/lib/sse.ts)는 event 이름 + data(JSON)를
    무변환 소비한다.
    """

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for ev in progress_hub.subscribe(session_id):
                yield {
                    "event": ev["event"],
                    "data": json.dumps(ev, ensure_ascii=False),
                }
        except Exception as exc:  # noqa: BLE001
            err = {"event": "error", "message": str(exc)}
            yield {"event": "error", "data": json.dumps(err, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
