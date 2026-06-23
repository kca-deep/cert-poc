"""
parsing.py — 입력 파일을 '## N.' 형식 Markdown으로 변환하는 어댑터.

CLI/API 업로드 단계가 사용하는 단일 진입점. HWP 변환은 hwp_parser 를 재사용하고,
'## N.' 문항 분리는 이 모듈의 extract_all_questions() 로 self-contained 처리한다.

지원 포맷:
  - .hwp / .hwpx : hwp_parser.parse_hwp_to_blocks → blocks_to_exam_md
  - .md          : 그대로 읽어 반환
  - .pdf         : NotImplementedError (백엔드 pdfplumber 연동 후 지원)
"""

from __future__ import annotations

import re
from pathlib import Path

# core 패키지 로드 시 src/ 가 sys.path 에 등록되므로 평면 모듈을 그대로 import 한다.
import core  # noqa: F401  (sys.path 셋업 트리거)

from hwp_parser import parse_hwp_to_blocks, blocks_to_exam_md


def extract_all_questions(md_text: str) -> list[tuple[int, str]]:
    """'## N.' Markdown 에서 (문항번호, 문항블록) 목록을 반환한다 (self-contained)."""
    out: list[tuple[int, str]] = []
    for m in re.finditer(r"(## (\d+)\.\n[\s\S]*?)(?=\n## \d+\.|$)", md_text):
        out.append((int(m.group(2)), m.group(1).strip()))
    return out


def parse_to_md(file_path: str | Path) -> str:
    """
    입력 파일을 '## N.' 형식 Markdown 문자열로 변환해 반환한다.

    Args:
        file_path: .hwp / .hwpx / .md / .pdf 파일 경로.

    Returns:
        '## N.' 형식 시험지 Markdown 텍스트.

    Raises:
        NotImplementedError: .pdf (백엔드 연동 전).
        ValueError:          지원하지 않는 확장자.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".hwp", ".hwpx"):
        blocks = parse_hwp_to_blocks(path)
        return blocks_to_exam_md(blocks, source_title=path.stem)

    if suffix == ".md":
        return path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        raise NotImplementedError("PDF 파싱은 백엔드 pdfplumber 연동 후 지원")

    raise ValueError(f"지원하지 않는 파일 형식: {suffix}")


def extract_questions_from_md(md_text: str) -> list[dict]:
    """
    '## N.' Markdown에서 문항 목록을 [{"qNumber", "mdText"}, ...] 형태로 추출한다.

    extract_all_questions()의 (번호, 블록) 튜플을 dict로 변환한다.
    API/업로드 파싱 단계가 사용한다.

    개행을 LF로 정규화한다: 업로드 바이트를 decode('utf-8')하면 CRLF(\\r\\n)가
    남아 '## N.\\n' 정규식 매칭이 실패하므로(브라우저/Windows 파일), 여기서 흡수한다.
    """
    normalized = md_text.replace("\r\n", "\n").replace("\r", "\n")
    return [
        {"qNumber": q_num, "mdText": block}
        for q_num, block in extract_all_questions(normalized)
    ]
