"""
code_checker.py — Layer 0 규칙 기반 이상 탐지 (LLM 불필요)

대상 유형: A01, A03, A13, A15, A17, A18
- 선택지 구조 및 지문 참조 오류를 정규식·집합 연산으로 탐지
- grouped-v2에서 100% 미탐이었던 유형들을 코드로 완전 대체

사용법:
    python src/code_checker.py data/파일.md
    python src/code_checker.py data/파일.md --q 13
"""

import json
import re
import sys
from pathlib import Path

CHOICE_SYMBOLS = ["①", "②", "③", "④"]
CHOICE_SET     = set(CHOICE_SYMBOLS)

# ㉠~㉣ 원문자 마커 (지문 내 항목 표시)
CIRCLE_MARKERS = {"㉠", "㉡", "㉢", "㉣"}

# ①~④를 지문 마커로 쓰는 경우도 포함 (A17 대응)
# 단, 선택지 구역과 구분: 선택지 이전(지문/stem) 구역에서만 확인
PASSAGE_MARKERS = CIRCLE_MARKERS | set(CHOICE_SYMBOLS)

# A18: 지문 참조를 암시하는 stem 패턴
PASSAGE_REF_PATTERNS = [
    r"다음.*?을\s*보고",                          # "다음 ~을 보고"
    r"다음.*?을\s*읽고",                          # "다음 ~을 읽고"
    r"다음\s+문장",                               # "다음 문장"
    r"다음은\s+.{2,30}(이다|입니다)",             # "다음은 ... 이다"
    r"다음\s+(표|그림|자료|기사|신문|보기|지문)",  # "다음 표/그림/자료/기사..."
    r"\[지문\]",
    r"아래.*?(표|그림|자료|참고)",
]

# A18 탐지 제외 패턴 — 지문이 없는 것이 정상인 stem 형식
PASSAGE_NON_REF_PATTERNS = [
    r"다음\s+중",                                        # "다음 중 ~것은?"
    r"다음.*?에\s*대한\s*설명으로",                      # "다음 X에 대한 설명으로"
    r"다음.*?으로\s*(옳|틀|바르|적합|알맞)",              # "다음 ~으로 옳은/틀린 것은?"
    r"다음\s+(개인정보|정보보호|법령|조항|규정|원칙|제도)", # "다음 개인정보 X에 대한..."
]

# A15: 선택지 텍스트 최소 의미 길이 (이 미만이면 빈 것으로 간주)
MIN_CHOICE_TEXT_LEN = 2


# ── 선택지 추출 유틸 ──────────────────────────────────────────

def extract_choices(question_block: str) -> list[tuple[str, str]]:
    """
    선택지 줄에서 (기호, 전체텍스트) 순서 리스트 반환.
    멀티라인 선택지(다음 줄이 ①~④로 시작하지 않으면 이전 선택지의 계속)도 처리.
    예: [("①", "㉠ 개인정보처리자\n㉡ 개인정보담당자"), ...]
    """
    choices: list[tuple[str, list[str]]] = []
    for line in question_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in CHOICE_SET:
            sym = stripped[0]
            text = stripped[1:].strip()
            choices.append((sym, [text]))
        elif choices:
            # 이전 선택지의 연속 줄
            choices[-1][1].append(stripped)
    return [(sym, "\n".join(lines).strip()) for sym, lines in choices]


def extract_question_number(question_block: str) -> int | None:
    m = re.search(r"^## (\d+)\.", question_block, re.MULTILINE)
    return int(m.group(1)) if m else None


# ── 각 유형 탐지 함수 ─────────────────────────────────────────

def check_a01(q_num: int, question_block: str) -> dict:
    """A01 보기 중복: 동일 텍스트가 두 선택지 이상에 존재."""
    choices = extract_choices(question_block)
    texts = [t for _, t in choices if t]
    seen: dict[str, str] = {}  # text → 처음 등장한 기호
    dupes = []
    for sym, text in choices:
        if not text:
            continue
        norm = re.sub(r"\s+", " ", text).strip()
        if norm in seen:
            dupes.append({
                "location": f"choice_{CHOICE_SYMBOLS.index(sym)+1}",
                "original": f"{sym} {text}",
                "suspected": f"'{text}'가 {seen[norm]}와 동일한 텍스트",
                "suggested": "선택지 텍스트 수정 필요",
            })
        else:
            seen[norm] = sym

    if dupes:
        return _result(q_num, "A01", "보기 중복", True, dupes, "high")
    return _result(q_num, "A01", "보기 중복", False, [], "high")


def check_a03(q_num: int, question_block: str) -> dict:
    """A03 보기개수 미달: ①②③④ 중 하나 이상 없음."""
    choices = extract_choices(question_block)
    present = {sym for sym, _ in choices}
    missing = [s for s in CHOICE_SYMBOLS if s not in present]

    if missing:
        issues = [{
            "location": "choice_section",
            "original": f"등장 기호: {sorted(present)}",
            "suspected": f"선택지 {missing} 없음",
            "suggested": f"선택지 {missing} 추가 필요",
        }]
        return _result(q_num, "A03", "보기개수 미달", True, issues, "high")
    return _result(q_num, "A03", "보기개수 미달", False, [], "high")


def check_a13(q_num: int, question_block: str) -> dict:
    """A13 문항번호 중복: 동일 기호가 두 번 이상 등장."""
    choices = extract_choices(question_block)
    sym_count: dict[str, int] = {}
    for sym, _ in choices:
        sym_count[sym] = sym_count.get(sym, 0) + 1

    dupes = {s: c for s, c in sym_count.items() if c > 1}
    if dupes:
        issues = [{
            "location": "choice_section",
            "original": str(dict(sym_count)),
            "suspected": f"중복 기호: {list(dupes.keys())}",
            "suggested": "선택지 번호 순서 수정 필요",
        }]
        return _result(q_num, "A13", "문항번호 중복", True, issues, "high")
    return _result(q_num, "A13", "문항번호 중복", False, [], "high")


def check_a15(q_num: int, question_block: str) -> dict:
    """A15 보기 없음: 기호는 있으나 바로 뒤 텍스트가 없거나 의미 없는 경우."""
    choices = extract_choices(question_block)
    empty = []
    for sym, text in choices:
        # 텍스트가 없거나 MIN_CHOICE_TEXT_LEN 미만이면 빈 것으로 간주
        if len(text) < MIN_CHOICE_TEXT_LEN:
            idx = CHOICE_SYMBOLS.index(sym) + 1
            display = repr(text) if text else "빈 문자열"
            empty.append({
                "location": f"choice_{idx}",
                "original": f"{sym} {text}".strip(),
                "suspected": f"'{sym}' 기호 뒤 텍스트 없음 (텍스트={display})",
                "suggested": "선택지 텍스트 작성 필요",
            })
    if empty:
        return _result(q_num, "A15", "보기 없음", True, empty, "high")
    return _result(q_num, "A15", "보기 없음", False, [], "high")


def check_a17(q_num: int, question_block: str) -> dict:
    """A17 지문 원문자 탈자: 선택지가 ㉠~㉣(또는 ①~④)를 참조하는데 지문에 마커가 없음."""
    lines = question_block.splitlines()

    # 지문/stem 구역(선택지 이전)과 선택지 구역 분리
    passage_lines: list[str] = []
    choice_lines:  list[str] = []
    in_choices = False
    for line in lines:
        stripped = line.strip()
        if stripped and stripped[0] in CHOICE_SET:
            in_choices = True
        if in_choices:
            choice_lines.append(line)
        else:
            passage_lines.append(line)

    passage_text = "\n".join(passage_lines)
    choices_text = "\n".join(choice_lines)

    # 선택지 텍스트에 ㉠~㉣ 참조 여부 확인
    circle_refs = CIRCLE_MARKERS & set(choices_text)

    # 선택지가 ①~④를 "항목 참조 마커"로 쓰는지 확인
    # (선택지 기호 자체가 아닌, 선택지 텍스트 내 인용용 ①~④)
    # 예: "① ㉠ A ㉡ B" 에서 선택지 텍스트 내부에 ①~④가 있는 경우
    choice_texts_only = " ".join(t for _, t in extract_choices(question_block))
    num_refs_in_text = set(CHOICE_SYMBOLS) & set(choice_texts_only)

    # 지문에서 참조된 마커 존재 확인
    passage_circle_markers  = CIRCLE_MARKERS     & set(passage_text)
    passage_num_markers     = set(CHOICE_SYMBOLS) & set(passage_text)

    missing = []

    # ㉠~㉣ 마커: 선택지에서 참조됐는데 지문에 없는 것
    missing_circle = circle_refs - passage_circle_markers
    if missing_circle:
        missing.extend(sorted(missing_circle))

    # ①~④ 마커: 선택지 텍스트 내에서 항목으로 참조됐는데 지문에 없는 것
    # (단, 선택지 구역 자체의 ①~④는 제외 — 지문 내 인용 목적만)
    if num_refs_in_text and not passage_num_markers:
        # 지문에 ①~④가 전혀 없고, 선택지 텍스트 내에서 참조 중
        missing.extend(sorted(num_refs_in_text))

    if missing:
        issues = [{
            "location": "passage",
            "original": (
                f"선택지 참조 마커: {sorted(circle_refs | num_refs_in_text)}, "
                f"지문 내 마커: {sorted(passage_circle_markers | passage_num_markers)}"
            ),
            "suspected": f"지문에서 {missing} 마커 누락",
            "suggested": "지문에 원문자 마커 추가 필요",
        }]
        return _result(q_num, "A17", "지문 원문자 탈자", True, issues, "high")
    return _result(q_num, "A17", "지문 원문자 탈자", False, [], "high")


def check_a18(q_num: int, question_block: str) -> dict:
    """A18 문장 전체 생략: stem이 지문을 참조하나 지문 블록이 없음."""
    lines = question_block.splitlines()

    # stem 추출 (## N. 다음 줄 ~ 첫 선택지 이전)
    stem_lines = []
    in_stem = False
    for line in lines:
        if re.match(r"^## \d+\.", line):
            in_stem = True
            continue
        if in_stem:
            if line.strip() and line.strip()[0] in CHOICE_SET:
                break
            stem_lines.append(line)
    stem = "\n".join(stem_lines)

    # 지문 참조가 아닌 패턴이면 즉시 false (오탐 방지)
    if any(re.search(p, stem) for p in PASSAGE_NON_REF_PATTERNS):
        return _result(q_num, "A18", "문장 전체 생략", False, [], "high")

    # stem이 지문 참조 패턴을 포함하는지
    refers_to_passage = any(re.search(p, stem) for p in PASSAGE_REF_PATTERNS)
    if not refers_to_passage:
        return _result(q_num, "A18", "문장 전체 생략", False, [], "high")

    # 지문 블록 존재 여부 (선택지 이전에 인용 블록이나 본문 내용이 있는지)
    # stem 이후 선택지 이전 사이에 실질 텍스트가 있으면 지문 존재로 간주
    non_empty_stem_lines = [l for l in stem_lines if l.strip()]

    # stem이 "다음 문장에서 설명하는 것은?" 한 줄뿐이면 지문 없음
    if len(non_empty_stem_lines) <= 1:
        issues = [{
            "location": "passage",
            "original": stem.strip(),
            "suspected": "지문 참조 표현이 있으나 지문 블록이 없음",
            "suggested": "지문 내용 추가 필요",
        }]
        return _result(q_num, "A18", "문장 전체 생략", True, issues, "medium")

    return _result(q_num, "A18", "문장 전체 생략", False, [], "high")


# ── 공통 결과 포맷 ────────────────────────────────────────────

def _result(q_num: int, type_code: str, type_name: str,
            found: bool, issues: list, confidence: str) -> dict:
    return {
        "question_number": q_num,
        "type_code": type_code,
        "type_name": type_name,
        "found": found,
        "issues": issues,
        "confidence": confidence,
        "layer": 0,
        "method": "code",
    }


# ── 문항 추출 ─────────────────────────────────────────────────

def extract_all_questions(md_text: str) -> list[tuple[int, str]]:
    """MD 파일에서 (문항번호, 문항블록) 목록 반환."""
    questions = []
    for m in re.finditer(r"(## \d+\.\n[\s\S]*?)(?=\n## \d+\.|$)", md_text):
        block = m.group(1).strip()
        q_num = extract_question_number(block)
        if q_num is not None:
            questions.append((q_num, block))
    return questions


# ── 전체 실행 ─────────────────────────────────────────────────

CHECKERS = [check_a01, check_a03, check_a13, check_a15, check_a17, check_a18]
TYPE_NAMES = ["A01", "A03", "A13", "A15", "A17", "A18"]


def run_code_check(md_path: Path, q_filter: int | None = None,
                   output_dir: Path | None = None) -> list[dict]:
    """전체 문항에 대해 6개 유형 코드 검사 실행."""
    md_text = md_path.read_text(encoding="utf-8")
    questions = extract_all_questions(md_text)
    results = []

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    found_count = 0
    for q_num, block in questions:
        if q_filter is not None and q_num != q_filter:
            continue

        for checker in CHECKERS:
            r = checker(q_num, block)
            results.append(r)

            if output_dir:
                label    = f"Q{q_num:02d}_{r['type_code']}"
                out_path = output_dir / f"{label}.json"
                out_path.write_text(json.dumps(r, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

            if r["found"]:
                found_count += 1
                t  = r["type_code"]
                q  = r["question_number"]
                og = r["issues"][0]["original"] if r["issues"] else ""
                print(f"  [FOUND] Q{q:02d}-{t}  {og[:60]}")

    total = len(questions) * len(CHECKERS)
    print(f"\n[code_checker] {len(questions)}문항 × {len(CHECKERS)}유형 = {total}건 검사"
          f"  →  found={found_count}")
    return results


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Layer 0 코드 기반 이상 탐지")
    parser.add_argument("md", help="입력 MD 파일 경로")
    parser.add_argument("--q",      type=int, default=None, help="특정 문항만")
    parser.add_argument("--outdir", type=str, default=None, help="결과 저장 디렉토리")
    args = parser.parse_args()

    md_path    = Path(args.md)
    output_dir = Path(args.outdir) if args.outdir else None

    print(f"[code_checker] 파일: {md_path.name}")
    run_code_check(md_path, q_filter=args.q, output_dir=output_dir)


if __name__ == "__main__":
    main()
