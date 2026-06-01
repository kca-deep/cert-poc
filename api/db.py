"""
db.py — SQLite 세션 영속 계층 (webapp_plan §4 스키마 축약).

표준 라이브러리 sqlite3 만 사용 (외부 의존성 0).
저장 컬럼은 snake_case, 외부로 나가는 dict 는 web/lib/types.ts 와 일치하는
camelCase 로 매핑한다 (라우터가 그대로 Pydantic 모델에 넣을 수 있도록).

테이블:
    sessions        (id, created_at, original_filename, file_type, status,
                     question_count, found_count, elapsed_seconds, md_text)
    questions       (session_id, q_number, md_text)
    anomaly_results (session_id, q_number, type_code, layer, found,
                     confidence, issues(JSON), filtered, filter_reason)
    review_actions  (session_id, q_number, type_code, action, comment,
                     updated_at)  ← 담당자 검수 결정 영속 (PK 3컬럼, upsert)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from . import config

DB_PATH: Path = config.RESULT_ROOT / "cert.db"

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
    provider          TEXT NOT NULL DEFAULT 'local'
);

CREATE TABLE IF NOT EXISTS questions (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number    INTEGER NOT NULL,
    md_text     TEXT NOT NULL,
    PRIMARY KEY (session_id, q_number)
);

CREATE TABLE IF NOT EXISTS anomaly_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number      INTEGER NOT NULL,
    type_code     TEXT NOT NULL,
    layer         INTEGER NOT NULL,
    found         INTEGER NOT NULL DEFAULT 0,
    confidence    TEXT,
    issues        TEXT NOT NULL DEFAULT '[]',
    filtered      INTEGER NOT NULL DEFAULT 0,
    filter_reason TEXT
);

CREATE TABLE IF NOT EXISTS review_actions (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number    INTEGER NOT NULL,
    type_code   TEXT NOT NULL,
    action      TEXT NOT NULL,
    comment     TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, q_number, type_code)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_session ON anomaly_results(session_id);
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
        conn.executescript(_SCHEMA)
        _migrate(conn)


def reconcile_stuck_sessions() -> int:
    """
    미완료(uploading/parsing/running) 상태로 남은 세션을 error 로 정리한다.

    진행은 progress_hub 의 인메모리 daemon 스레드로만 추적되므로, 서버가 재시작되거나
    분석 중 프로세스가 끊기면 그 상태 전이(done/error)가 영속되지 못한 채 DB 에
    'running' 이 박제된다(LLM 접속 불가로 매 호출이 블로킹되다 재시작되는 경우 등).
    새 프로세스 startup 시점에는 _RUNS 가 비어 있어 미완료 행은 모두 고아이므로,
    여기서 일괄 error 로 내려 목록에서 '분석중'으로 영원히 남는 것을 막는다.
    (단일 uvicorn 워커 가정 — webapp_plan §0.)

    Returns: 정리된 행 수.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE sessions SET status='error' "
            "WHERE status IN ('uploading','parsing','running')"
        )
        return cur.rowcount


def _migrate(conn: sqlite3.Connection) -> None:
    """기존 DB 에 누락된 컬럼을 더한다 (멱등). 신규 컬럼은 여기서만 추가."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    if "provider" not in cols:
        conn.execute(
            "ALTER TABLE sessions ADD COLUMN provider TEXT NOT NULL DEFAULT 'local'"
        )


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
    }


def _result_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "qNumber": row["q_number"],
        "typeCode": row["type_code"],
        "layer": row["layer"],
        "found": bool(row["found"]),
        "confidence": row["confidence"],
        "issues": json.loads(row["issues"] or "[]"),
        "filtered": bool(row["filtered"]),
        "filterReason": row["filter_reason"],
    }


# ── 쓰기 ─────────────────────────────────────────────────────────

def _safe(s: str) -> str:
    """
    SQLite(UTF-8) write 전 문자열을 surrogate-safe 하게 정규화.
    깨진 멀티파트 파일명 등이 surrogate escape('\\udcXX')로 들어오면 sqlite3 가
    UnicodeEncodeError 를 던지므로, 인코딩 불가 문자를 ��(U+FFFD)로 치환한다.
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
                question_count, found_count, elapsed_seconds, md_text, provider)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
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


def reset_for_rerun(session_id: str, provider: str) -> None:
    """재실행 준비: 상태를 running 으로, 집계 초기화, 공급자 갱신, 기존 결과 삭제."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE sessions
               SET status='running', found_count=0, elapsed_seconds=NULL,
                   provider=?
               WHERE id=?""",
            (provider, session_id),
        )
        conn.execute("DELETE FROM anomaly_results WHERE session_id = ?", (session_id,))


def delete_session(session_id: str) -> bool:
    """세션 1건 삭제. CASCADE로 questions/anomaly_results/review_actions 동반 삭제.
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


def replace_results(session_id: str, results: list[dict[str, Any]]) -> None:
    """세션의 anomaly_results 를 전량 교체 (camelCase dict 리스트)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM anomaly_results WHERE session_id = ?", (session_id,))
        conn.executemany(
            """INSERT INTO anomaly_results
               (session_id, q_number, type_code, layer, found, confidence,
                issues, filtered, filter_reason)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (
                    session_id,
                    int(r["qNumber"]),
                    r["typeCode"],
                    int(r["layer"]),
                    1 if r.get("found") else 0,
                    r.get("confidence"),
                    json.dumps(r.get("issues", []), ensure_ascii=False),
                    1 if r.get("filtered") else 0,
                    r.get("filterReason"),
                )
                for r in results
            ],
        )


# ── 읽기 ─────────────────────────────────────────────────────────

def list_sessions() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()
    return [_session_row_to_dict(r) for r in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    """SessionDetail dict (session/questions/results, camelCase) 또는 None."""
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
        rrows = conn.execute(
            "SELECT * FROM anomaly_results WHERE session_id = ? ORDER BY q_number, type_code",
            (session_id,),
        ).fetchall()
    return {
        "session": _session_row_to_dict(srow),
        "questions": [
            {"qNumber": r["q_number"], "mdText": r["md_text"]} for r in qrows
        ],
        "results": [_result_row_to_dict(r) for r in rrows],
    }


# ── 검수 결정 (review_actions) ───────────────────────────────────

def list_reviews(session_id: str) -> list[dict[str, Any]]:
    """세션의 검수 결정 목록 (camelCase: qNumber/typeCode/action/comment)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q_number, type_code, action, comment
               FROM review_actions WHERE session_id = ?
               ORDER BY q_number, type_code""",
            (session_id,),
        ).fetchall()
    return [
        {
            "qNumber": r["q_number"],
            "typeCode": r["type_code"],
            "action": r["action"],
            "comment": r["comment"],
        }
        for r in rows
    ]


def upsert_review(session_id: str, q_number: int, type_code: str,
                  action: str, comment: str | None, updated_at: str) -> None:
    """검수 결정 1건 upsert (PK: session_id+q_number+type_code)."""
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO review_actions
               (session_id, q_number, type_code, action, comment, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (session_id, int(q_number), type_code, action,
             _safe(comment) if isinstance(comment, str) else comment, updated_at),
        )


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
