"""
group_run.py — 5개 그룹 프롬프트로 이상 탐지 실행 (per-type 비교용)

사용법:
    python src/group_run.py                          # 전체 실행
    python src/group_run.py --reset                  # 기존 결과 무시하고 재실행
    python src/group_run.py --q 3                    # Q03만
    python src/group_run.py --group G1               # G1 그룹만
    python src/group_run.py --input data/파일.md     # 입력 MD 파일 지정

출력: results/grouped/Q{nn}_{Gx}.json
      results/grouped/Q{nn}_{Gx}_ERROR.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("openai 패키지가 필요합니다: pip install openai")

from config import lm_config, print_lm_config

ROOT       = Path(__file__).parent.parent
PROMPT_DIR = ROOT / "prompts"
DATA_PATH  = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR = ROOT / "results" / "grouped"

CFG         = lm_config()
BASE_URL    = CFG["base_url"]
MODEL       = CFG["model"]
MAX_RETRIES = CFG["max_retries"]
RETRY_DELAY = CFG["retry_delay"]

GROUP_CONFIGS = [
    {"code": "G1", "file": "G1_typo_spelling.md",      "types": ["A02","A04","A05","A06","A16"]},
    {"code": "G2", "file": "G2_question_structure.md",  "types": ["A01","A03","A10","A13","A15","A17","A18"]},
    {"code": "G3", "file": "G3_sentence_quality.md",    "types": ["A07","A08"]},
    {"code": "G4", "file": "G4_legal_domain.md",        "types": ["A09","A19","A20"]},
    {"code": "G5", "file": "G5_editorial.md",           "types": ["A11","A12","A14"]},
]


# ── 공통 유틸 (full_run.py와 동일) ───────────────────────────

def extract_all_question_numbers(md_text: str) -> list[int]:
    return sorted(int(m) for m in re.findall(r"^## (\d+)\.", md_text, re.MULTILINE))


def load_preamble() -> str:
    return (PROMPT_DIR / "_shared" / "system_preamble.md").read_text(encoding="utf-8")


def load_group_prompt(filename: str) -> str:
    path = PROMPT_DIR / "grouped" / filename
    if not path.exists():
        raise FileNotFoundError(f"그룹 프롬프트 없음: {path}")
    return path.read_text(encoding="utf-8")


def extract_question(md_text: str, n: int) -> str:
    m = re.search(rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)", md_text)
    if not m:
        raise ValueError(f"문항 {n}번을 찾을 수 없습니다.")
    return m.group(1).strip()


def sanitize(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("> "):
            lines.append("(지문) " + line[2:])
        elif line == ">":
            lines.append("(지문)")
        else:
            lines.append(line)
    return "\n".join(lines)


def build_messages(preamble: str, group_prompt: str, question_block: str) -> list[dict]:
    user_content = sanitize(group_prompt).replace("{{QUESTION_BLOCK}}", sanitize(question_block))
    return [
        {"role": "system", "content": preamble},
        {"role": "user",   "content": user_content},
    ]


# ── LLM 호출 ────────────────────────────────────────────────

class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_lm_studio(messages: list[dict], slot_id: int = -1) -> dict:
    client = OpenAI(base_url=BASE_URL, api_key="lm-studio",
                    timeout=CFG["timeout"], max_retries=0)
    extra: dict = {
        "cache_prompt": CFG.get("cache_prompt", False),
    }
    # reasoning_effort 는 gpt-oss 계열만 지원 (Ollama 등은 thinking 요청으로 해석해 거부).
    if "gpt-oss" in (MODEL or "").lower():
        extra["reasoning_effort"] = CFG["reasoning_effort"]
    if slot_id >= 0:
        extra["slot_id"] = slot_id
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=CFG["temperature"],
        max_tokens=CFG["max_tokens"],
        extra_body=extra,
    )
    raw = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    blocks = re.findall(r"```(?:json)?\s*([\s\S]+?)```", raw)
    candidates = blocks if blocks else [raw]
    last_error = None
    for candidate in reversed(candidates):
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            last_error = e
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise LMCallError(
            f"JSON 파싱 실패 (finish={finish}): {last_error or e}",
            raw=raw[:2000],
        )


def call_with_retry(messages: list[dict], label: str, slot_id: int = -1) -> dict | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            return call_lm_studio(messages, slot_id=slot_id)
        except LMCallError as e:
            if attempt < MAX_RETRIES:
                print(f"  [재시도 {attempt+1}/{MAX_RETRIES}] {e}")
                time.sleep(RETRY_DELAY)
            else:
                return {"_error": str(e), "_raw": e.raw}
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"  [재시도 {attempt+1}/{MAX_RETRIES}] 호출 실패: {e}")
                time.sleep(RETRY_DELAY)
            else:
                return {"_error": str(e), "_raw": ""}


# ── 결과 요약 출력 ────────────────────────────────────────────

def summarize_result(result: dict) -> str:
    """그룹 결과 요약: 탐지된 유형 코드 리스트 반환."""
    if "_error" in result:
        return "ERROR"
    found_types = [r["type_code"] for r in result.get("results", []) if r.get("found")]
    if found_types:
        return f"found={','.join(found_types)}"
    return "none"


# ── 메인 실행 ────────────────────────────────────────────────

def run_all(q_filter: int | None, group_filter: str | None, reset: bool):
    print_lm_config(CFG)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    x_text   = DATA_PATH.read_text(encoding="utf-8")
    preamble = load_preamble()
    questions = extract_all_question_numbers(x_text)

    groups = [g for g in GROUP_CONFIGS
              if group_filter is None or g["code"] == group_filter]

    pairs = [
        (q, g)
        for q in questions
        for g in groups
        if q_filter is None or q == q_filter
    ]
    total = len(pairs)

    done = skipped = errors = 0

    for i, (q_num, grp) in enumerate(pairs, 1):
        label    = f"Q{q_num:02d}_{grp['code']}"
        out_path = RESULT_DIR / f"{label}.json"
        err_path = RESULT_DIR / f"{label}_ERROR.json"

        if not reset and (out_path.exists() or err_path.exists()):
            print(f"[{i:3d}/{total}] {label} — 스킵")
            skipped += 1
            continue

        print(f"[{i:3d}/{total}] {label} ...", end=" ", flush=True)
        t0 = time.time()

        try:
            group_prompt   = load_group_prompt(grp["file"])
            question_block = extract_question(x_text, q_num)
            messages       = build_messages(preamble, group_prompt, question_block)
        except Exception as e:
            print(f"준비 실패: {e}")
            err_path.write_text(
                json.dumps({"question_number": q_num, "group_code": grp["code"],
                            "_error": str(e)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            errors += 1
            continue

        n_slots = CFG.get("n_slots", 4)
        slot_id = (i - 1) % n_slots if CFG.get("slot_round_robin", False) else -1
        result  = call_with_retry(messages, label, slot_id=slot_id)
        elapsed = time.time() - t0

        if result and "_error" in result:
            err_path.write_text(
                json.dumps({"question_number": q_num, "group_code": grp["code"],
                            "_error": result["_error"], "_raw": result.get("_raw", "")},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"에러 ({elapsed:.1f}s)")
            errors += 1
        else:
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary = summarize_result(result)
            print(f"{summary}  ({elapsed:.1f}s)")
            done += 1

    print(f"\n[완료] 성공={done}  스킵={skipped}  에러={errors}  합계={total}")


def main():
    global RESULT_DIR, DATA_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--q",      type=int, help="특정 문항 번호만 실행")
    parser.add_argument("--group",  type=str, help="특정 그룹만 실행 (예: G1)")
    parser.add_argument("--reset",  action="store_true", help="기존 결과 무시하고 재실행")
    parser.add_argument("--outdir", type=str, default=None, help="결과 저장 디렉토리")
    parser.add_argument("--input",  type=str, default=None, help="입력 MD 파일 경로")
    args = parser.parse_args()

    if args.input:
        DATA_PATH = Path(args.input)
    if args.outdir:
        RESULT_DIR = Path(args.outdir)

    group_filter = args.group.upper() if args.group else None
    run_all(q_filter=args.q, group_filter=group_filter, reset=args.reset)


if __name__ == "__main__":
    main()
