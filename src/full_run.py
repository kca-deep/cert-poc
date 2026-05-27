"""
full_run.py — A01~A20 × Q01~Q20 = 400 콜 전체 실행 러너

사용법:
    python src/full_run.py              # 전체 400 콜 (기존 결과 스킵)
    python src/full_run.py --reset      # 기존 결과 무시하고 전체 재실행
    python src/full_run.py --q 3        # Q03만 (20 콜)
    python src/full_run.py --type A09   # A09만 (20 콜)

출력: results/full_run/Q{nn}_{Axx}.json  (정상)
      results/full_run/Q{nn}_{Axx}_ERROR.json  (에러)
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

ROOT = Path(__file__).parent.parent

CFG = lm_config()
BASE_URL    = CFG["base_url"]
MODEL       = CFG["model"]
MAX_RETRIES = CFG["max_retries"]
RETRY_DELAY = CFG["retry_delay"]

ALL_TYPES = [f"A{n:02d}" for n in range(1, 21)]
ALL_QUESTIONS = list(range(1, 21))

PROMPT_DIR  = ROOT / "prompts"
DATA_PATH   = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR  = ROOT / "results" / "full_run"   # --outdir 으로 재할당 가능


# ── 공통 유틸 ────────────────────────────────────────────────

def load_preamble() -> str:
    return (PROMPT_DIR / "_shared" / "system_preamble.md").read_text(encoding="utf-8")


def load_type_prompt(code: str) -> str:
    matches = list((PROMPT_DIR / "per-type").glob(f"{code}_*.md"))
    if not matches:
        raise FileNotFoundError(f"프롬프트 파일 없음: {code}_*.md")
    return matches[0].read_text(encoding="utf-8")


def extract_question(md_text: str, n: int) -> str:
    pattern = rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)"
    m = re.search(pattern, md_text)
    if not m:
        raise ValueError(f"문항 {n}번을 찾을 수 없습니다.")
    return m.group(1).strip()


def sanitize(text: str) -> str:
    """gpt-oss-20b: '>' 블록쿼트 → '(지문) ' 치환으로 degenerate 루프 방지."""
    lines = []
    for line in text.splitlines():
        if line.startswith("> "):
            lines.append("(지문) " + line[2:])
        elif line == ">":
            lines.append("(지문)")
        else:
            lines.append(line)
    return "\n".join(lines)


def build_messages(preamble: str, type_prompt: str, question_block: str) -> list[dict]:
    user_content = sanitize(type_prompt).replace("{{QUESTION_BLOCK}}", sanitize(question_block))
    return [
        {"role": "system", "content": preamble},
        {"role": "user",   "content": user_content},
    ]


class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_lm_studio(messages: list[dict], slot_id: int = -1) -> dict:
    # max_retries=0: OpenAI 클라이언트 내부 자동 재시도 비활성화 (우리 래퍼가 담당)
    client = OpenAI(base_url=BASE_URL, api_key="lm-studio",
                    timeout=CFG["timeout"], max_retries=0)
    extra: dict = {
        "reasoning_effort": CFG["reasoning_effort"],
        # cache_prompt:false = 이전 슬롯 KV 캐시를 재사용하지 않고 매 요청을 처음부터 인코딩.
        # 슬롯 간 prefix 공유로 인한 KV 상태 오염을 원천 차단 (성능 대신 완전 격리).
        "cache_prompt": CFG.get("cache_prompt", False),
    }
    if slot_id >= 0:
        extra["slot_id"] = slot_id  # 명시적 슬롯 고정 (라운드로빈 사용 시)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=CFG["temperature"],
        max_tokens=CFG["max_tokens"],
        extra_body=extra,
    )
    raw = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    rt = (resp.usage.completion_tokens_details.reasoning_tokens
          if resp.usage and resp.usage.completion_tokens_details else "?")
    # Extract all code-fenced JSON blocks, prefer the last one (model often self-corrects)
    blocks = re.findall(r"```(?:json)?\s*([\s\S]+?)```", raw)
    candidates = blocks if blocks else [raw]
    last_error = None
    for candidate in reversed(candidates):
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            last_error = e
    # Fallback: try stripping fences from full raw
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise LMCallError(
            f"JSON 파싱 실패 (finish={finish}, reasoning_tokens={rt}): {last_error or e}",
            raw=raw[:2000],
        )


CHOICE_SYMBOLS = {"①", "②", "③", "④"}
CHOICE_SYM_TO_NUM = {"①": "1번", "②": "2번", "③": "3번", "④": "4번"}


def choice_symbols_present(question_block: str) -> set[str]:
    """Return set of ①②③④ that actually appear as line-starters in the choice section."""
    present: set[str] = set()
    for line in question_block.splitlines():
        stripped = line.strip()
        if stripped and stripped[0] in CHOICE_SYMBOLS:
            present.add(stripped[0])
    return present


def postprocess_a15(result: dict, question_block: str) -> dict:
    """A15 post-processor: if model claims a symbol has blank text but that symbol
    doesn't appear as a choice line-starter in the question, override to found:false."""
    if result.get("type_code") != "A15" or not result.get("found"):
        return result
    present = choice_symbols_present(question_block)
    if not present:
        return result
    original = ""
    if result.get("issues"):
        original = result["issues"][0].get("original", "")
    suspected = ""
    if result.get("issues"):
        suspected = result["issues"][0].get("suspected", "")
    # Check each symbol: if model claims it in original/suspected but it's not present → FP
    for sym in CHOICE_SYMBOLS:
        if sym not in present and (sym in original or CHOICE_SYM_TO_NUM[sym] in suspected):
            result = dict(result)
            result["found"] = False
            result["issues"] = []
            result["_note"] = f"후처리 수정: '{sym}' 기호가 선택지에 없음 (present={sorted(present)})"
            return result
    return result


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


# ── 메인 실행 ────────────────────────────────────────────────

def run_all(q_filter: int | None, type_filter: str | None, reset: bool):
    print_lm_config(CFG)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    x_text  = DATA_PATH.read_text(encoding="utf-8")
    preamble = load_preamble()

    pairs = [
        (q, code)
        for q in ALL_QUESTIONS
        for code in ALL_TYPES
        if (q_filter is None or q == q_filter)
        and (type_filter is None or code == type_filter)
    ]
    total = len(pairs)

    done = skipped = errors = 0

    for i, (q_num, code) in enumerate(pairs, 1):
        label = f"Q{q_num:02d}_{code}"
        out_path   = RESULT_DIR / f"{label}.json"
        err_path   = RESULT_DIR / f"{label}_ERROR.json"

        if not reset and (out_path.exists() or err_path.exists()):
            print(f"[{i:3d}/{total}] {label} — 스킵")
            skipped += 1
            continue

        print(f"[{i:3d}/{total}] {label} ...", end=" ", flush=True)
        t0 = time.time()

        try:
            type_prompt    = load_type_prompt(code)
            question_block = extract_question(x_text, q_num)
            messages       = build_messages(preamble, type_prompt, question_block)
        except Exception as e:
            print(f"준비 실패: {e}")
            err_path.write_text(
                json.dumps({"question_number": q_num, "type_code": code,
                            "_error": str(e), "found": None},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            errors += 1
            continue

        # 라운드로빈 슬롯: 연속 호출이 같은 슬롯에 몰려 KV 캐시를 공유하는 것을 방지.
        # cache_prompt:false와 함께 쓰면 슬롯 수준의 완전 격리.
        n_slots = CFG.get("n_slots", 4)
        slot_id = (i - 1) % n_slots if CFG.get("slot_round_robin", False) else -1
        result = call_with_retry(messages, label, slot_id=slot_id)
        if result and "_error" not in result and code == "A15":
            result = postprocess_a15(result, question_block)
        elapsed = time.time() - t0

        if result and "_error" in result:
            err_path.write_text(
                json.dumps({"question_number": q_num, "type_code": code,
                            "_error": result["_error"],
                            "_raw":   result.get("_raw", ""),
                            "found":  None},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"에러 ({elapsed:.1f}s) → {err_path.name}")
            errors += 1
        else:
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            found = result.get("found")
            conf  = result.get("confidence", "?")
            print(f"{'found' if found else 'none ':5s}  conf={conf}  ({elapsed:.1f}s)")
            done += 1

    print(f"\n[완료] 성공={done}  스킵={skipped}  에러={errors}  합계={total}")


def main():
    global RESULT_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--q",      type=int,  help="특정 문항 번호만 실행")
    parser.add_argument("--type",   type=str,  help="특정 유형 코드만 실행 (예: A09)")
    parser.add_argument("--reset",  action="store_true", help="기존 결과 무시하고 재실행")
    parser.add_argument("--outdir", type=str,  default=None,
                        help="결과 저장 디렉토리 (기본: results/full_run)")
    args = parser.parse_args()

    if args.outdir:
        RESULT_DIR = Path(args.outdir)

    type_filter = args.type.upper() if args.type else None
    run_all(q_filter=args.q, type_filter=type_filter, reset=args.reset)


if __name__ == "__main__":
    main()
