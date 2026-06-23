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
from typing import AsyncIterator, Literal

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
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
    model: str | None = None  # 분석 시점 실제 모델 id (gpt-oss/exaone 구분)


class Question(BaseModel):
    qNumber: int
    mdText: str


class Finding(BaseModel):
    """holistic 검출 오류 1건 (web/lib/types.ts Finding 미러, camelCase)."""
    id: str
    qNumber: int
    location: str = ""
    quote: str = ""
    errorType: str = "기타"
    reason: str = ""
    suggestion: str = ""
    confidence: str = "보통"


class SessionDetail(BaseModel):
    session: Session
    questions: list[Question] = []
    findings: list[Finding] = []


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
    """담당자 검수 결정 (web/lib/types.ts ReviewAction 미러, finding 단위)."""
    findingId: str
    action: Literal["confirmed", "rejected", "pending"]
    comment: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_provider(explicit: str | None) -> str:
    """src/config.py 의 단일 정의로 공급자를 해석한다 (기본값 일원화)."""
    from config import resolve_provider  # src/ 는 api.config import 시 sys.path 등록됨
    return resolve_provider(explicit)


def _preflight_provider(provider: str) -> str | None:
    """
    분석 시작 전 공급자 가용성을 동기 점검하고, 채택된 모델 id 를 반환한다
    (빈 세션 생성/고착 방지 + 분석 시점 모델 기록용).
    - local: 후보(8080/8081)를 프로브해 살아있는 서버의 실제 모델 id 반환, 전부
      응답 없으면 503.
    - claude: 외부 핑 대신 ANTHROPIC_API_KEY 존재로 게이트, CLAUDE_MODEL 반환.
    """
    from config import build_config, claude_configured
    if provider == "claude":
        if not claude_configured():
            raise HTTPException(
                status_code=503,
                detail="Claude API 키(ANTHROPIC_API_KEY)가 설정되지 않았습니다.",
            )
        return build_config(provider).get("claude_model")
    from core.pipeline import preflight_local
    cfg = build_config(provider)
    msg = preflight_local(cfg)  # 성공 시 cfg["model"] 에 채택 모델 주입
    if msg:
        raise HTTPException(status_code=503, detail=msg)
    return cfg.get("model")


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
        findings=[Finding(**f) for f in detail["findings"]],
    )


# ── DELETE /sessions/{id} ────────────────────────────────────────
@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, bool]:
    """세션 1건 삭제 (questions/findings/review_actions CASCADE). 없으면 404."""
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
    model = _preflight_provider(provider)  # LLM 미가용이면 503, 가용이면 채택 모델 id

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
        "model": model,
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
    model = _preflight_provider(provider)  # 가용성 확인 + 재실행 시점 모델 기록

    db.reset_for_rerun(session_id, provider, model)
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
    db.upsert_review(session_id, req.findingId,
                     req.action, req.comment, _now_iso())
    return {"ok": True}


# ── GET /sessions/{id}/export ────────────────────────────────────
_EXPORT_MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/sessions/{session_id}/export")
async def export_reviews(
    session_id: str,
    format: Literal["xlsx", "pdf"] = Query("xlsx"),
) -> Response:
    """
    검수 결과를 검증결과 파일로 내보낸다. 탐지 항목이 '전부 확인(confirmed)'이면
    확인 항목만, 확인이 0건이거나 일부만 확인됐으면 전체 탐지 항목을 출력한다(검수상태
    컬럼 포함). 파일명: {원본문서명}_{timestamp}_검증결과.{xlsx|pdf}.
    내보낼 탐지 항목이 없으면 400, 세션 없으면 404.
    """
    if db.get_status(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    from .. import export  # 지연 import (openpyxl/reportlab 미설치 시 앱 기동 보호)

    if not export.has_findings(session_id):
        raise HTTPException(status_code=400, detail="내보낼 탐지 항목이 없습니다.")

    # export 시각 기준 타임스탬프 (YYYYMMDD_HHMMSS).
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = export.export_filename(session_id, format, timestamp)

    try:
        if format == "pdf":
            stem = filename.rsplit(".", 1)[0]
            content = export.build_pdf(session_id, title=stem)
        else:
            content = export.build_xlsx(session_id)
    except ImportError as exc:  # 라이브러리 미설치
        raise HTTPException(
            status_code=500,
            detail=f"export 라이브러리 미설치: {exc}. pip install -r api/requirements.txt",
        ) from exc

    # 한글 파일명 → RFC 5987 filename*=UTF-8'' (브라우저 호환 위해 filename= 도 병기).
    ascii_fallback = quote(filename)  # 비-ASCII 안전한 폴백
    disposition = (
        f"attachment; filename=\"{ascii_fallback}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=content,
        media_type=_EXPORT_MEDIA[format],
        headers={"Content-Disposition": disposition},
    )


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
