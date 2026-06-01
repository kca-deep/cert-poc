"""
upload.py — 파일 업로드 + 파싱 엔드포인트.

    POST /upload?mode=parse   파일 업로드 후 ParseResult 반환

응답은 web/lib/types.ts 의 ParseResult (camelCase) 를 미러링한다:
    { filename, fileType, sizeBytes, questionCount, questions, mergedMd, warnings }

core.parsing 이 준비되면 실제 파싱을, 없으면 합성 ParseResult 로 폴백한다 →
파이프라인 미준비 상태에서도 엔드포인트가 동작/테스트 가능.
"""

from __future__ import annotations

from typing import Any, Literal

import aiofiles
from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

from .. import config

router = APIRouter(tags=["upload"])


# ── Pydantic 모델 (web/lib/types.ts ParseResult 미러) ────────────

class Question(BaseModel):
    qNumber: int
    mdText: str


class ParseWarning(BaseModel):
    qNumber: int | None = None
    severity: Literal["warning", "info"] = "info"
    message: str


class ParseResult(BaseModel):
    filename: str
    fileType: Literal["hwp", "hwpx", "pdf"]
    sizeBytes: int
    questionCount: int
    questions: list[Question]
    mergedMd: str
    warnings: list[ParseWarning]


def _guess_file_type(filename: str) -> str:
    low = filename.lower()
    if low.endswith(".hwpx"):
        return "hwpx"
    if low.endswith(".pdf"):
        return "pdf"
    return "hwp"


def _synthetic_parse(filename: str, size: int, raw_text: str | None) -> ParseResult:
    """core.parsing 미준비 시 사용하는 합성 결과 (엔드포인트 테스트용)."""
    md = raw_text or (
        "# 1. 합성 예시 문항\n\n"
        "다음 중 옳은 것은?\n\n"
        "1) 보기1\n2) 보기2\n3) 보기3\n4) 보기4\n"
    )
    return ParseResult(
        filename=filename,
        fileType=_guess_file_type(filename),  # type: ignore[arg-type]
        sizeBytes=size,
        questionCount=1,
        questions=[Question(qNumber=1, mdText=md)],
        mergedMd=md,
        warnings=[
            ParseWarning(
                severity="info",
                message="core.parsing 미준비 — 합성 결과를 반환했습니다 (스켈레톤).",
            )
        ],
    )


# ── POST /upload ─────────────────────────────────────────────────
@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    mode: str = Query("parse"),
) -> ParseResult:
    """
    파일 업로드. mode=parse (기본) → 업로드 디렉토리에 저장 후 ParseResult 반환.
    core.parsing 이 import 가능하고 .md 파일이면 실제 파싱, 아니면 합성 폴백.
    """
    filename = file.filename or "upload.bin"
    dest = config.UPLOAD_ROOT / filename

    # 비동기 저장
    content = await file.read()
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
    size = len(content)

    # .md 텍스트면 디코드 시도 (실파싱/합성 양쪽에서 활용).
    # 개행을 LF로 정규화: CRLF 가 남으면 '## N.\n' 정규식 매칭이 실패해
    # 문항이 0개로 잡힌다 (브라우저/Windows 업로드).
    raw_text: str | None = None
    if filename.lower().endswith(".md"):
        try:
            raw_text = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            raw_text = None

    # ── core.parsing 지연 import (없거나 실패해도 폴백) ──
    try:
        from core.parsing import (  # type: ignore  # noqa
            extract_questions_from_md,
            parse_to_md,
        )
    except Exception:
        return _synthetic_parse(filename, size, raw_text)

    try:
        if raw_text is not None:
            merged_md = raw_text
        else:
            # 비-md 파일: 실제 변환 (HWP/HWPX/PDF → md)
            merged_md = parse_to_md(dest)  # type: ignore[misc]

        q_items: list[dict[str, Any]] = extract_questions_from_md(merged_md)  # type: ignore[misc]
        questions = [
            Question(qNumber=int(q["qNumber"]), mdText=str(q["mdText"]))
            for q in q_items
        ]
        return ParseResult(
            filename=filename,
            fileType=_guess_file_type(filename),  # type: ignore[arg-type]
            sizeBytes=size,
            questionCount=len(questions),
            questions=questions,
            mergedMd=merged_md,
            warnings=[],
        )
    except Exception as exc:  # noqa: BLE001 — 파싱 실패 시 합성 폴백 + 경고
        res = _synthetic_parse(filename, size, raw_text)
        res.warnings.append(
            ParseWarning(severity="warning", message=f"실파싱 실패: {exc}")
        )
        return res
