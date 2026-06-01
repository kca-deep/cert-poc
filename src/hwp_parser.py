"""
hwp_parser.py — HWP → "## N." 형식 Markdown 변환기

kordoc CLI(Node.js, 로컬 캐시)를 subprocess로 호출해 blocks[] JSON을 받은 뒤
시험지 문항 구조(## N. + 선택지)로 변환합니다. 폐쇄망 환경에서 동작합니다.

사용법:
    python src/hwp_parser.py data/파일.hwp -o data/output.md
    python src/hwp_parser.py data/파일.hwp          # 같은 폴더에 .md 저장
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── kordoc 로컬 경로 ─────────────────────────────────────────
# 우선순위: .env의 KORDOC_CLI_PATH > npx 캐시 글롭 탐색 (OS 무관)
import shutil

# npx 캐시 루트 후보 (OS별). 각 하위에 <hash>/node_modules/kordoc/dist/cli.js 존재.
_NPX_CACHE_ROOTS = [
    Path.home() / "AppData/Local/npm-cache/_npx",  # Windows
    Path.home() / ".npm/_npx",                      # Linux/macOS
]


def _find_kordoc_cli() -> Path:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    # 1) 명시적 환경변수
    env_path = os.getenv("KORDOC_CLI_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2) npx 캐시를 글롭으로 탐색 (해시 디렉터리명은 환경마다 다름)
    for root in _NPX_CACHE_ROOTS:
        if not root.exists():
            continue
        matches = sorted(root.glob("*/node_modules/kordoc/dist/cli.js"))
        if matches:
            return matches[0]

    raise FileNotFoundError(
        "kordoc CLI를 찾을 수 없습니다. .env에 KORDOC_CLI_PATH를 설정하거나 "
        "`npx -y kordoc <파일>` 을 한 번 실행해 캐시를 생성하세요."
    )


def _find_node() -> str:
    # 1) 명시적 환경변수
    env_node = os.getenv("NODE_BIN")
    if env_node:
        return env_node

    # 2) PATH 탐색 (Windows: node.exe / which 대신 shutil.which — OS 무관)
    found = shutil.which("node")
    if found:
        return found

    # 3) 알려진 설치 경로 (nvm 등)
    for candidate in [
        Path.home() / ".nvm/versions/node/v20.19.5/bin/node",
        Path("/usr/local/bin/node"),
        Path("/usr/bin/node"),
        Path("C:/Program Files/nodejs/node.exe"),
    ]:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError("node 실행 파일을 찾을 수 없습니다. PATH에 추가하거나 NODE_BIN 설정.")


# ── 핵심: kordoc CLI 호출 ─────────────────────────────────────

def parse_hwp_to_blocks(hwp_path: str | Path) -> list[dict]:
    """HWP 파일을 kordoc CLI로 파싱해 IRBlock[] 반환."""
    hwp_path = Path(hwp_path).resolve()
    if not hwp_path.exists():
        raise FileNotFoundError(f"HWP 파일 없음: {hwp_path}")

    node_bin = _find_node()
    kordoc_cli = _find_kordoc_cli()

    result = subprocess.run(
        [node_bin, str(kordoc_cli), str(hwp_path), "--format", "json", "--silent"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"kordoc 실행 실패 (exit {result.returncode}): {result.stderr[:500]}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"kordoc JSON 파싱 실패: {e}\n출력 앞부분: {result.stdout[:300]}")

    if not data.get("success"):
        raise RuntimeError(f"kordoc 파싱 오류: {data.get('error', '알 수 없음')}")

    return data.get("blocks", [])


# ── IRBlock → ## N. 형식 변환 ─────────────────────────────────

CHOICE_SYMBOLS = ["①", "②", "③", "④"]
_NESTED_TABLE_RE = re.compile(r"\[중첩 테이블 #\d+\]")
_QUESTION_NUM_RE = re.compile(r"^(\d+)\.$")


def _clean_text(text: str) -> str:
    """[중첩 테이블 #N] 마커 제거 + 앞뒤 공백 정리."""
    return _NESTED_TABLE_RE.sub("", text).strip()


def _is_exam_header(block: dict) -> bool:
    """수험번호/성명 등 시험지 상단 헤더 테이블."""
    if block.get("type") != "table":
        return False
    cells = block.get("table", {}).get("cells", [])
    if not cells or not cells[0]:
        return False
    text = cells[0][0].get("text", "")
    return "국가" in text or "자격" in text or "수험번호" in text


def _is_section_header(block: dict) -> tuple[bool, str]:
    """섹션 구분 테이블인지 판별 → (True, 섹션명) 또는 (False, '')."""
    if block.get("type") != "table":
        return False, ""
    cells = block.get("table", {}).get("cells", [])
    if len(cells) == 1 and len(cells[0]) == 1:
        text = cells[0][0].get("text", "")
        cleaned = _clean_text(text)
        if cleaned and len(cleaned) < 30:
            return True, cleaned
    return False, ""


def _extract_question_num(block: dict) -> int | None:
    """문항 테이블에서 문항 번호 추출. 아니면 None."""
    if block.get("type") != "table":
        return None
    cells = block.get("table", {}).get("cells", [])
    if not cells or not cells[0]:
        return None
    first_text = cells[0][0].get("text", "").strip()
    m = _QUESTION_NUM_RE.match(first_text)
    return int(m.group(1)) if m else None


_CHOICE_SET = set(CHOICE_SYMBOLS)

def _extract_choices(cells: list[list[dict]]) -> list[str]:
    """선택지 기호와 텍스트를 HWP 원본 순서 그대로 추출. 중복 기호도 보존."""
    choices: list[str] = []
    for row in cells:
        for i, cell in enumerate(row):
            sym = cell.get("text", "").strip()
            if sym not in _CHOICE_SET:
                continue
            if i + 1 < len(row):
                next_text = row[i + 1].get("text", "").strip()
                content = "" if next_text in _CHOICE_SET else next_text
            else:
                content = ""
            choices.append(f"{sym} {content}".rstrip())
    return choices


def _table_block_to_question_md(block: dict) -> str:
    """문항 테이블 블록을 ## N.\n문항텍스트\n①②③④ 형식으로 변환."""
    cells = block["table"]["cells"]

    # 문항 번호
    q_num = cells[0][0].get("text", "").strip().rstrip(".")

    # 문항 텍스트 (row0, col1): 보기 포함
    raw_question = cells[0][1].get("text", "") if len(cells[0]) > 1 else ""
    question_text = _clean_text(raw_question)

    # 선택지
    choices = _extract_choices(cells)

    lines = [f"## {q_num}."]
    if question_text:
        lines.append(question_text)
    if choices:
        lines.append("")
        lines.extend(choices)
    return "\n".join(lines)


def blocks_to_exam_md(blocks: list[dict], source_title: str = "") -> str:
    """IRBlock[] → 시험지 ## N. 형식 Markdown."""
    parts: list[str] = []
    if source_title:
        parts.append(f"# {source_title}\n")

    for block in blocks:
        if _is_exam_header(block):
            continue

        is_sec, sec_name = _is_section_header(block)
        if is_sec:
            parts.append(f"\n## [{sec_name}]\n")
            continue

        if _extract_question_num(block) is not None:
            parts.append(_table_block_to_question_md(block))
            continue

        # paragraph/heading 등 나머지 블록은 스킵 (시험지엔 없음)

    return "\n\n".join(parts).strip()


# ── 통합 진입점 ───────────────────────────────────────────────

def hwp_to_md(hwp_path: str | Path, output_path: str | Path | None = None) -> Path:
    """HWP → ## N. Markdown 변환 후 저장. 저장 경로 반환."""
    hwp_path = Path(hwp_path)

    if output_path is None:
        output_path = hwp_path.with_suffix(".md")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[hwp_parser] 파싱 중: {hwp_path.name}")
    blocks = parse_hwp_to_blocks(hwp_path)
    print(f"[hwp_parser] blocks {len(blocks)}개 수신")

    md = blocks_to_exam_md(blocks, source_title=hwp_path.stem)
    output_path.write_text(md, encoding="utf-8")
    print(f"[hwp_parser] 저장 완료: {output_path}  ({len(md)} chars)")
    return output_path


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="HWP → ## N. Markdown 변환기 (kordoc 기반)")
    parser.add_argument("hwp", help="변환할 HWP 파일 경로")
    parser.add_argument("-o", "--output", default=None, help="출력 .md 파일 경로 (기본: HWP와 같은 폴더)")
    args = parser.parse_args()

    out = hwp_to_md(args.hwp, args.output)
    print(f"\n완료: {out}")


if __name__ == "__main__":
    main()
