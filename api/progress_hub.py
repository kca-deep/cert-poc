"""
progress_hub.py — 백그라운드 파이프라인 실행 + SSE 이벤트 버퍼.

webapp_plan §0 "백그라운드 비동기 + 재방문" UX:
  - POST /sessions 가 hub.start() 로 run_pipeline 을 별도 스레드에서 구동.
  - 진행 이벤트는 인메모리 버퍼에 누적되고 DB 에 최종 결과가 영속된다.
  - GET /sessions/{id}/progress 가 hub.subscribe() 로 버퍼를 tail 구독 →
    SSE 끊겨도 재접속 시 처음부터 replay, 다중 구독 가능.

단일 uvicorn 워커 가정(개발). 서버 재시작 시 진행 중 세션 버퍼는 사라지지만
done 세션은 DB 에 영속되므로 재방문 시 결과가 보인다.

run_pipeline 은 동기 제너레이터이므로 daemon 스레드에서 소비한다.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator

import anyio

from . import config, db

# 세션별 실행 상태
#   events: 누적 ProgressEvent(dict)
#   done:   파이프라인 종료 여부
_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


# ── type_code → layer 도출 (pipeline 정의 재사용, 단일 소스) ──────

def _layer_of_map() -> dict[str, int]:
    """core.pipeline 의 레이어 정의로 type_code → layer 매핑을 만든다."""
    from core.pipeline import LAYER0_TYPES, LAYER1_GROUPS, LAYER2_TYPES

    m: dict[str, int] = {}
    for t in LAYER0_TYPES:
        m[t] = 0
    for grp in LAYER1_GROUPS:
        for t in grp["types"]:
            m[t] = 1
    for t in LAYER2_TYPES:
        m[t] = 2
    return m


def _results_from_filtered(filtered: dict[str, Any]) -> list[dict[str, Any]]:
    """
    merged_filtered.json({q_str: {type_code: result}}) → AnomalyResult dict 리스트.
    found=true 인 것(또는 후처리로 필터된 것)만 적재한다.
    """
    layer_of = _layer_of_map()
    out: list[dict[str, Any]] = []
    for q_str, q_results in filtered.items():
        try:
            q_num = int(q_str)
        except (TypeError, ValueError):
            continue
        for type_code, r in q_results.items():
            if not isinstance(r, dict):
                continue
            found = bool(r.get("found"))
            filter_reason = r.get("_filtered") or r.get("_note")
            is_filtered = filter_reason is not None
            if not found and not is_filtered:
                continue  # 미탐은 적재 생략 (프론트는 found/filtered 만 사용)
            out.append({
                "qNumber": q_num,
                "typeCode": type_code,
                "layer": layer_of.get(type_code, 2),
                "found": found,
                "confidence": r.get("confidence"),
                "issues": r.get("issues", []) or [],
                "filtered": is_filtered,
                "filterReason": filter_reason if isinstance(filter_reason, str) else None,
            })
    return out


def _persist_on_done(session_id: str, result_dir: Path,
                     total_found: int, elapsed: float) -> None:
    """done 이벤트 처리: merged_filtered → anomaly_results 적재 + 세션 done."""
    import json

    filtered_path = result_dir / "merged_filtered.json"
    if filtered_path.exists():
        filtered = json.loads(filtered_path.read_text(encoding="utf-8"))
        results = _results_from_filtered(filtered)
        db.replace_results(session_id, results)
    db.update_session_status(session_id, "done", found_count=total_found,
                             elapsed_seconds=elapsed)


# ── 백그라운드 러너 ──────────────────────────────────────────────

def _run(session_id: str, md_text: str, result_dir: Path,
         q_filter: int | None, provider: str | None, reset: bool) -> None:
    """별도 스레드에서 run_pipeline 을 소비하며 버퍼/DB 를 갱신한다."""
    from core.pipeline import run_pipeline

    run = _RUNS[session_id]
    try:
        for ev in run_pipeline(md_text, result_dir, q_filter=q_filter,
                               reset=reset, provider=provider):
            with _LOCK:
                run["events"].append(ev)
            kind = ev.get("event")
            if kind == "done":
                _persist_on_done(
                    session_id, result_dir,
                    int(ev.get("totalFound", 0)),
                    float(ev.get("elapsed", 0.0)),
                )
            elif kind == "error":
                db.update_session_status(session_id, "error")
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            run["events"].append({"event": "error", "message": str(exc)})
        db.update_session_status(session_id, "error")
    finally:
        with _LOCK:
            run["done"] = True


def start(session_id: str, md_text: str, result_dir: Path,
          q_filter: int | None = None, provider: str | None = None,
          reset: bool = False) -> None:
    """세션 분석을 백그라운드 스레드로 시작 (이미 실행 중이면 무시)."""
    with _LOCK:
        if session_id in _RUNS and not _RUNS[session_id]["done"]:
            return
        _RUNS[session_id] = {"events": [], "done": False}
    t = threading.Thread(
        target=_run,
        args=(session_id, md_text, result_dir, q_filter, provider, reset),
        daemon=True, name=f"pipeline-{session_id}",
    )
    t.start()


def is_active(session_id: str) -> bool:
    with _LOCK:
        return session_id in _RUNS


# ── SSE 구독 (async) ─────────────────────────────────────────────

async def subscribe(session_id: str) -> AsyncIterator[dict[str, Any]]:
    """
    버퍼를 tail 구독. 이미 쌓인 이벤트를 먼저 replay 한 뒤, 새 이벤트가 생기면
    이어서 yield 하고, done 에 도달하면 종료한다.

    hub 에 실행 이력이 없으면(서버 재시작 후 등) DB 상태로 폴백:
      - done  → 저장된 결과 기반 done 이벤트 1회 emit
      - error → error 이벤트
      - 그 외 → 아무것도 못 찾음 메시지
    """
    if not is_active(session_id):
        async for ev in _replay_from_db(session_id):
            yield ev
        return

    cursor = 0
    while True:
        with _LOCK:
            run = _RUNS.get(session_id)
            events = list(run["events"]) if run else []
            done = run["done"] if run else True
        while cursor < len(events):
            yield events[cursor]
            cursor += 1
        if done and cursor >= len(events):
            return
        await anyio.sleep(0.15)


async def _replay_from_db(session_id: str) -> AsyncIterator[dict[str, Any]]:
    detail = db.get_session(session_id)
    if detail is None:
        yield {"event": "error", "message": "session not found"}
        return
    status = detail["session"]["status"]
    if status == "done":
        yield {
            "event": "done",
            "totalFound": detail["session"]["foundCount"],
            "elapsed": detail["session"].get("elapsedSeconds") or 0.0,
        }
    elif status == "error":
        yield {"event": "error", "message": "이전 실행에서 오류로 종료되었습니다."}
    else:
        # 진행 중이었으나 서버 재시작 등으로 버퍼 유실
        yield {"event": "error", "message": "진행 정보가 없습니다. 다시 시작해 주세요."}
