"""
events.py — 파이프라인 진행상황 이벤트 (공유 계약, 단일 소스).

run_pipeline()이 yield 하는 ProgressEvent의 형태를 정의한다. CLI는 이를 받아
print 하고, FastAPI는 그대로 JSON 직렬화해 SSE로 스트리밍한다.

★ 키 네이밍은 프론트엔드 web/lib/types.ts 의 ProgressEvent 유니온과 **정확히
  동일한 camelCase** 를 사용한다 (totalQ, typeCode, totalFound, ...).
  이렇게 해야 프론트가 무변환으로 소비하고, 추후 web/lib/sse.ts 를 실서버로
  바꿀 때 "EventSource 연결"만으로 끝난다. (webapp_plan §5의 snake_case 예시
  대신 프론트 타입을 정본으로 채택.)

이벤트 종류 (event 필드로 구분):
  - layer_start    : { event, layer, totalQ? }
  - q_layer0_done  : { event, q, types: {typeCode: bool} }
  - q_type_done    : { event, layer, q, typeCode, found, confidence? }
  - layer_done     : { event, layer, found }
  - postprocess    : { event, filtered }
  - done           : { event, totalFound, elapsed }
  - error          : { event, message }
"""

from __future__ import annotations

from typing import Literal, TypedDict


class LayerStart(TypedDict, total=False):
    event: Literal["layer_start"]
    layer: int
    totalQ: int


class QLayer0Done(TypedDict):
    event: Literal["q_layer0_done"]
    q: int
    types: dict[str, bool]


class QTypeDone(TypedDict, total=False):
    event: Literal["q_type_done"]
    layer: int
    q: int
    typeCode: str
    found: bool
    confidence: str


class LayerDone(TypedDict):
    event: Literal["layer_done"]
    layer: int
    found: int


class Postprocess(TypedDict):
    event: Literal["postprocess"]
    filtered: int


class Done(TypedDict):
    event: Literal["done"]
    totalFound: int
    elapsed: float


class ErrorEvent(TypedDict):
    event: Literal["error"]
    message: str


ProgressEvent = (
    LayerStart
    | QLayer0Done
    | QTypeDone
    | LayerDone
    | Postprocess
    | Done
    | ErrorEvent
)


# ── 생성 헬퍼 (호출부 가독성용, 선택적 사용) ──────────────────────

def layer_start(layer: int, total_q: int | None = None) -> ProgressEvent:
    ev: LayerStart = {"event": "layer_start", "layer": layer}
    if total_q is not None:
        ev["totalQ"] = total_q
    return ev


def q_layer0_done(q: int, types: dict[str, bool]) -> ProgressEvent:
    return {"event": "q_layer0_done", "q": q, "types": types}


def q_type_done(
    layer: int, q: int, type_code: str, found: bool, confidence: str | None = None
) -> ProgressEvent:
    ev: QTypeDone = {
        "event": "q_type_done",
        "layer": layer,
        "q": q,
        "typeCode": type_code,
        "found": found,
    }
    if confidence:
        ev["confidence"] = confidence
    return ev


def layer_done(layer: int, found: int) -> ProgressEvent:
    return {"event": "layer_done", "layer": layer, "found": found}


def postprocess(filtered: int) -> ProgressEvent:
    return {"event": "postprocess", "filtered": filtered}


def done(total_found: int, elapsed: float) -> ProgressEvent:
    return {"event": "done", "totalFound": total_found, "elapsed": elapsed}


def error(message: str) -> ProgressEvent:
    return {"event": "error", "message": message}
