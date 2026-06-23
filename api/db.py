"""
db.py — SQLite 세션 영속 계층 (holistic findings 모델).

표준 라이브러리 sqlite3 만 사용 (외부 의존성 0).
저장 컬럼은 snake_case, 외부로 나가는 dict 는 web/lib/types.ts 와 일치하는
camelCase 로 매핑한다 (라우터가 그대로 Pydantic 모델에 넣을 수 있도록).

★ 전면 대체: 유형단위 anomaly_results(복합 키 q+type_code) → 문항/오류 단위
  findings(PK finding_id "<q>-<index>"). 검수(review_actions)도 finding_id 기준.
  과거 A코드 데이터는 컷오버(단절) — 레거시 테이블은 _migrate 에서 폐기한다.

테이블:
    sessions       (id, created_at, original_filename, file_type, status,
                    question_count, found_count, elapsed_seconds, md_text,
                    provider, model)
    questions      (session_id, q_number, md_text)
    findings       (session_id, finding_id, q_number, location, quote,
                    error_type, reason, suggestion, confidence)  ← 오류 1건/행
    review_actions (session_id, finding_id, action, comment, updated_at)
                                                  ← 검수 결정 영속 (finding 단위 upsert)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from . import config

DB_PATH: Path = config.RESULT_ROOT / "cert.db"

_REVIEW_DDL = """
CREATE TABLE IF NOT EXISTS review_actions (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    finding_id  TEXT NOT NULL,
    action      TEXT NOT NULL,
    comment     TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, finding_id)
);
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_type         TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'uploading',
    question_count    INTEGER NOT NULL DEFAULT 0,
    found_count       INTEGER NOT NULL DEFAULT 0,
    elapsed_seconds   REAL,
    md_text           TEXT NOT NULL DEFAULT '',
    provider          TEXT NOT NULL DEFAULT 'local',
    model             TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number    INTEGER NOT NULL,
    md_text     TEXT NOT NULL,
    PRIMARY KEY (session_id, q_number)
);

CREATE TABLE IF NOT EXISTS findings (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    finding_id  TEXT NOT NULL,
    q_number    INTEGER NOT NULL,
    location    TEXT NOT NULL DEFAULT '',
    quote       TEXT NOT NULL DEFAULT '',
    error_type  TEXT NOT NULL DEFAULT '기타',
    reason      TEXT NOT NULL DEFAULT '',
    suggestion  TEXT NOT NULL DEFAULT '',
    confidence  TEXT NOT NULL DEFAULT '보통',
    PRIMARY KEY (session_id, finding_id)
);
""" + _REVIEW_DDL + """
CREATE INDEX IF NOT EXISTS idx_findings_session ON findings(session_id);
CREATE INDEX IF NOT EXISTS idx_questions_session ON questions(session_id);
CREATE INDEX IF NOT EXISTS idx_reviews_session ON review_actions(session_id);
"""


def get_conn() -> sqlite3.Connection:
    """새 연결 반환. 백그라운드 스레드에서도 안전하도록 매 작업마다 연다."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """스키마 생성 (멱등). 앱 startup 에서 호출."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        _migrate(conn)
        conn.executescript(_SCHEMA)


def reconcile_stuck_sessions() -> int:
    """
    미완료(uploading/parsing/running) 상태로 남은 세션을 error 로 정리한다.

    진행은 progress_hub 의 인메모리 daemon 스레드로만 추적되므로, 서버가 재시작되거나
    분석 중 프로세스가 끊기면 그 상태 전이(done/error)가 영속되지 못한 채 DB 에
    'running' 이 박제된다. 새 프로세스 startup 시점에는 미완료 행이 모두 고아이므로
    여기서 일괄 error 로 내려 목록에서 '분석중'으로 영원히 남는 것을 막는다.

    Returns: 정리된 행 수.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE sessions SET status='error' "
            "WHERE status IN ('uploading','parsing','running')"
        )
        return cur.rowcount


def _migrate(conn: sqlite3.Connection) -> None:
    """
    스키마 마이그레이션 (멱등). executescript(_SCHEMA) 보다 먼저 호출된다.

    - sessions 누락 컬럼(provider/model) 추가.
    - 컷오버: 레거시 유형단위 테이블(anomaly_results)과 type_code 기반 review_actions 를
      폐기한다(과거 A코드 검수 결과는 단절). 새 findings/review_actions 스키마는
      이후 executescript(_SCHEMA) 가 생성한다.
    """
    have = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    if "sessions" in have:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "provider" not in cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN provider TEXT NOT NULL DEFAULT 'local'"
            )
        if "model" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN model TEXT")

    # 레거시 유형단위 결과 테이블 폐기 (cutover).
    conn.execute("DROP TABLE IF EXISTS anomaly_results")

    # review_actions 가 구 스키마(type_code, finding_id 없음)면 폐기 후 재생성.
    if "review_actions" in have:
        rcols = {r["name"] for r in conn.execute("PRAGMA table_info(review_actions)")}
        if "finding_id" not in rcols:
            conn.execute("DROP TABLE IF EXISTS review_actions")


# ── 행 → camelCase dict 매핑 ─────────────────────────────────────

def _session_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "originalFilename": row["original_filename"],
        "fileType": row["file_type"],
        "status": row["status"],
        "questionCount": row["question_count"],
        "foundCount": row["found_count"],
        "elapsedSeconds": row["elapsed_seconds"],
        "provider": (row["provider"] if "provider" in row.keys() else "local"),
        "model": (row["model"] if "model" in row.keys() else None),
    }


def _finding_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["finding_id"],
        "qNumber": row["q_number"],
        "location": row["location"],
        "quote": row["quote"],
        "errorType": row["error_type"],
        "reason": row["reason"],
        "suggestion": row["suggestion"],
        "confidence": row["confidence"],
    }


# ── 쓰기 ─────────────────────────────────────────────────────────

def _safe(s: str) -> str:
    """
    SQLite(UTF-8) write 전 문자열을 surrogate-safe 하게 정규화.
    인코딩 불가 문자를 ��(U+FFFD)로 치환해 UnicodeEncodeError 를 막는다.
    """
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", "replace").decode("utf-8")


def create_session(session: dict[str, Any], md_text: str,
                   questions: list[dict[str, Any]]) -> None:
    """세션 + 문항 영속화. session 은 camelCase dict (POST /sessions)."""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, created_at, original_filename, file_type, status,
                question_count, found_count, elapsed_seconds, md_text, provider, model)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session["id"],
                session["createdAt"],
                _safe(session["originalFilename"]),
                session["fileType"],
                session.get("status", "running"),
                session.get("questionCount", len(questions)),
                session.get("foundCount", 0),
                session.get("elapsedSeconds"),
                _safe(md_text),
                session.get("provider", "local"),
                session.get("model"),
            ),
        )
        conn.executemany(
            "INSERT OR REPLACE INTO questions (session_id, q_number, md_text) VALUES (?,?,?)",
            [(session["id"], int(q["qNumber"]), _safe(str(q["mdText"])))
             for q in questions],
        )


def update_session_status(session_id: str, status: str,
                          found_count: int | None = None,
                          elapsed_seconds: float | None = None) -> None:
    sets = ["status = ?"]
    vals: list[Any] = [status]
    if found_count is not None:
        sets.append("found_count = ?")
        vals.append(found_count)
    if elapsed_seconds is not None:
        sets.append("elapsed_seconds = ?")
        vals.append(elapsed_seconds)
    vals.append(session_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", vals)


def reset_for_rerun(session_id: str, provider: str, model: str | None = None) -> None:
    """재실행 준비: 상태를 running 으로, 집계 초기화, 공급자·모델 갱신, 기존 결과 삭제."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE sessions
               SET status='running', found_count=0, elapsed_seconds=NULL,
                   provider=?, model=?
               WHERE id=?""",
            (provider, model, session_id),
        )
        conn.execute("DELETE FROM findings WHERE session_id = ?", (session_id,))


def delete_session(session_id: str) -> bool:
    """세션 1건 삭제. CASCADE로 questions/findings/review_actions 동반 삭제.
    삭제된 행이 있으면 True, 없으면(이미 없음) False."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0


def get_provider(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT provider FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return (row["provider"] if row and "provider" in row.keys() else None)


_FINDINGS_INSERT = """INSERT OR REPLACE INTO findings
    (session_id, finding_id, q_number, location, quote,
     error_type, reason, suggestion, confidence)
    VALUES (?,?,?,?,?,?,?,?,?)"""


def _finding_row(session_id: str, f: dict[str, Any]) -> tuple:
    return (
        session_id,
        str(f["id"]),
        int(f["qNumber"]),
        _safe(str(f.get("location", ""))),
        _safe(str(f.get("quote", ""))),
        _safe(str(f.get("errorType", "기타"))),
        _safe(str(f.get("reason", ""))),
        _safe(str(f.get("suggestion", ""))),
        _safe(str(f.get("confidence", "보통"))),
    )


def replace_findings(session_id: str, findings: list[dict[str, Any]]) -> None:
    """세션의 findings 를 전량 교체 (camelCase dict 리스트)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM findings WHERE session_id = ?", (session_id,))
        conn.executemany(
            _FINDINGS_INSERT, [_finding_row(session_id, f) for f in findings]
        )


def append_findings(session_id: str, findings: list[dict[str, Any]]) -> None:
    """
    findings 를 증분 추가한다 (분석 진행 중 q_done 마다 호출 → 실시간 영속).

    finding_id(PK)로 INSERT OR REPLACE 라 같은 문항을 다시 보내도 멱등하다.
    분석 중 페이지 이탈/서버 재시작 후 재방문해도 부분 결과가 남는다.
    """
    if not findings:
        return
    with get_conn() as conn:
        conn.executemany(
            _FINDINGS_INSERT, [_finding_row(session_id, f) for f in findings]
        )


# ── 읽기 ─────────────────────────────────────────────────────────

def list_sessions() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()
    return [_session_row_to_dict(r) for r in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    """SessionDetail dict (session/questions/findings, camelCase) 또는 None."""
    with get_conn() as conn:
        srow = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if srow is None:
            return None
        qrows = conn.execute(
            "SELECT q_number, md_text FROM questions WHERE session_id = ? ORDER BY q_number",
            (session_id,),
        ).fetchall()
        frows = conn.execute(
            """SELECT * FROM findings WHERE session_id = ?
               ORDER BY q_number, finding_id""",
            (session_id,),
        ).fetchall()
    return {
        "session": _session_row_to_dict(srow),
        "questions": [
            {"qNumber": r["q_number"], "mdText": r["md_text"]} for r in qrows
        ],
        "findings": [_finding_row_to_dict(r) for r in frows],
    }


# ── 검수 결정 (review_actions) ───────────────────────────────────

def list_reviews(session_id: str) -> list[dict[str, Any]]:
    """세션의 검수 결정 목록 (camelCase: findingId/action/comment)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT finding_id, action, comment
               FROM review_actions WHERE session_id = ?
               ORDER BY finding_id""",
            (session_id,),
        ).fetchall()
    return [
        {
            "findingId": r["finding_id"],
            "action": r["action"],
            "comment": r["comment"],
        }
        for r in rows
    ]


def upsert_review(session_id: str, finding_id: str,
                  action: str, comment: str | None, updated_at: str) -> None:
    """검수 결정 1건 upsert (PK: session_id+finding_id)."""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO review_actions
               (session_id, finding_id, action, comment, updated_at)
               VALUES (?,?,?,?,?)""",
            (session_id, str(finding_id), action,
             _safe(comment) if isinstance(comment, str) else comment, updated_at),
        )


def list_found_with_review(session_id: str) -> list[dict[str, Any]]:
    """
    탐지된 모든 finding + 검수상태를 조인해 반환 (export 전용).

    findings ⟕ review_actions 를 finding_id 로 묶어, 오류 상세(location/quote/
    errorType/reason/suggestion/confidence)에 검수 결정(action/comment)을 덧붙인다.
    미검수 항목은 action/comment 가 None.

    export.py 가 이 결과로 '확인 항목만(전부 확인 시)' vs '전체(미확인·일부확인 시)'를
    결정한다 — DB 는 전체를 주고 필터 정책은 export 가 갖는다(단일 소스).
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.finding_id, f.q_number, f.location, f.quote, f.error_type,
                      f.reason, f.suggestion, f.confidence, r.action, r.comment
               FROM findings f
               LEFT JOIN review_actions r
                 ON r.session_id = f.session_id
                AND r.finding_id = f.finding_id
               WHERE f.session_id = ?
               ORDER BY f.q_number, f.finding_id""",
            (session_id,),
        ).fetchall()
    return [
        {
            "id": r["finding_id"],
            "qNumber": r["q_number"],
            "location": r["location"],
            "quote": r["quote"],
            "errorType": r["error_type"],
            "reason": r["reason"],
            "suggestion": r["suggestion"],
            "confidence": r["confidence"],
            "action": r["action"],
            "comment": r["comment"],
        }
        for r in rows
    ]


def get_original_filename(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT original_filename FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return row["original_filename"] if row else None


def get_md_text(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT md_text FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return row["md_text"] if row else None


def get_status(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return row["status"] if row else None
