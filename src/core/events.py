"""
events.py — 파이프라인 진행상황 이벤트 (공유 계약, 단일 소스).

run_pipeline()이 yield 하는 ProgressEvent의 형태를 정의한다. CLI는 이를 받아
print 하고, FastAPI는 그대로 JSON 직렬화해 SSE로 스트리밍한다.

★ holistic 전환: 레이어/유형 단위 이벤트(layer_start·q_type_done·layer_done·
  postprocess)를 폐기하고 **문항 단위**(start·q_done·done·error)로 재정의했다.
  문항당 LLM 1콜 → findings[] 를 q_done 으로 흘린다.

★ 키 네이밍은 프론트엔드 web/lib/types.ts 의 ProgressEvent 유니온과 **정확히
  동일한 camelCase** 를 사용한다 (totalQ, hasError, totalFound, ...).
  findings 항목도 camelCase(errorType) 이다 — 한쪽을 바꾸면 반드시 양쪽을 맞춘다.

이벤트 종류 (event 필드로 구분):
  - start   : { event, totalQ }
  - q_start : { event, q, worker }          # 워커가 문항 처리를 시작(=active). worker=논리 레인(0~)
  - q_done  : { event, q, hasError, findings: Finding[], elapsedSeconds?, error? }
              # error 가 있으면 그 문항은 '검토 실패'(타임아웃/파싱오류) — 무오류 완료와 구분
  - done    : { event, totalFound, elapsed }
  - error   : { event, message }

Finding (findings[] 항목, camelCase):
  { id, location, quote, errorType, reason, suggestion, confidence }
  - id: 세션 내 안정 식별자 "<q>-<index>" (검수 finding 단위 PK)
  - errorType: 11-enum (맞춤법·띄어쓰기·문법비문·선택지누락·선택지중복·용어오류·
               사실오류·약어오기·정답유출·편집표시·기타)
  - confidence: 높음 | 보통 | 낮음
"""

from __future__ import annotations

from typing import Literal, TypedDict


class Finding(TypedDict, total=False):
    id: str
    location: str
    quote: str
    errorType: str
    reason: str
    suggestion: str
    confidence: str


class Start(TypedDict):
    event: Literal["start"]
    totalQ: int


class QStart(TypedDict):
    event: Literal["q_start"]
    q: int
    worker: int  # 논리 레인 인덱스(0~max_workers-1) → web 에서 agentA/B/C 로 표시


class QDone(TypedDict, total=False):
    event: Literal["q_done"]
    q: int
    hasError: bool
    findings: list[Finding]
    elapsedSeconds: float
    error: str  # 검토 실패(타임아웃/파싱오류) 메시지. 있으면 무오류 완료와 구분


class Done(TypedDict):
    event: Literal["done"]
    totalFound: int
    elapsed: float


class ErrorEvent(TypedDict):
    event: Literal["error"]
    message: str


ProgressEvent = Start | QStart | QDone | Done | ErrorEvent


# ── 생성 헬퍼 ─────────────────────────────────────────────────────

def start(total_q: int) -> ProgressEvent:
    return {"event": "start", "totalQ": total_q}


def q_start(q: int, worker: int = 0) -> ProgressEvent:
    return {"event": "q_start", "q": q, "worker": worker}


def q_done(
    q: int,
    findings: list[Finding],
    has_error: bool | None = None,
    elapsed_seconds: float | None = None,
    error: str | None = None,
) -> ProgressEvent:
    ev: QDone = {
        "event": "q_done",
        "q": q,
        "hasError": bool(findings) if has_error is None else has_error,
        "findings": findings,
    }
    if elapsed_seconds is not None:
        ev["elapsedSeconds"] = elapsed_seconds
    if error:
        ev["error"] = error
    return ev


def done(total_found: int, elapsed: float) -> ProgressEvent:
    return {"event": "done", "totalFound": total_found, "elapsed": elapsed}


def error(message: str) -> ProgressEvent:
    return {"event": "error", "message": message}
