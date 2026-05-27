"""
claude_run.py — full_run.py 와 동일 프롬프트/구조로 Claude Haiku 4.5 호출 비교 실행

LM Studio(gpt-oss-20b) 호출만 Anthropic SDK 로 교체. 프롬프트/sanitize/문항추출은 동일.
결과는 results/claude_haiku_run/ 에 저장하여 기존 gpt-oss-20b 결과(results/full_run/)와 분리.

사용법:
    python src/claude_run.py --dry        # dry_run 5쌍만 (A01×Q1, A02×Q2, A04×Q4, A06×Q6, A14×Q14)
    python src/claude_run.py --q 1        # Q01 한 줄 (20콜)
    python src/claude_run.py --type A09   # A09 한 줄 (20콜)
    python src/claude_run.py              # 전체 400콜
    python src/claude_run.py --reset      # 기존 결과 무시
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
    import anthropic
except ImportError:
    sys.exit("anthropic 패키지가 필요합니다: pip install anthropic")

from config import claude_config

ROOT = Path(__file__).parent.parent

_CCFG      = claude_config()
MODEL      = _CCFG["model"]
MAX_RETRIES = _CCFG["max_retries"]
RETRY_DELAY = _CCFG["retry_delay"]

ALL_TYPES     = [f"A{n:02d}" for n in range(1, 21)]
ALL_QUESTIONS = list(range(1, 21))

DRY_RUN_PAIRS = [
    ("A01", 1),
    ("A02", 2),
    ("A04", 4),
    ("A06", 6),
    ("A14", 14),
]

PROMPT_DIR = ROOT / "prompts"
DATA_PATH  = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR = ROOT / "results" / "claude_haiku_run"


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
    """gpt-oss-20b 와 동일 전처리 (Claude 에는 불필요하지만 동일 조건 비교 위해 유지)."""
    lines = []
    for line in text.splitlines():
        if line.startswith("> "):
            lines.append("(지문) " + line[2:])
        elif line == ">":
            lines.append("(지문)")
        else:
            lines.append(line)
    return "\n".join(lines)


def build_user_content(type_prompt: str, question_block: str) -> str:
    return sanitize(type_prompt).replace("{{QUESTION_BLOCK}}", sanitize(question_block))


class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_claude(client: anthropic.Anthropic, preamble: str, user_content: str) -> tuple[dict, dict]:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=_CCFG["max_tokens"],
        system=preamble,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = ""
    for block in resp.content:
        if block.type == "text":
            raw = block.text.strip()
            break
    finish = resp.stop_reason
    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean), usage
    except json.JSONDecodeError as e:
        raise LMCallError(
            f"JSON 파싱 실패 (stop={finish}): {e}",
            raw=raw[:2000],
        )


def call_with_retry(client: anthropic.Anthropic, preamble: str, user_content: str) -> tuple[dict | None, dict]:
    last_usage = {}
    for attempt in range(MAX_RETRIES + 1):
        try:
            result, usage = call_claude(client, preamble, user_content)
            return result, usage
        except LMCallError as e:
            if attempt < MAX_RETRIES:
                print(f"  [재시도 {attempt+1}/{MAX_RETRIES}] {e}")
                time.sleep(RETRY_DELAY)
            else:
                return {"_error": str(e), "_raw": e.raw}, last_usage
        except anthropic.APIStatusError as e:
            if attempt < MAX_RETRIES and e.status_code in (429, 500, 502, 503, 504, 529):
                print(f"  [재시도 {attempt+1}/{MAX_RETRIES}] {e.status_code} {e.message}")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                return {"_error": f"{e.status_code} {e.message}", "_raw": ""}, last_usage
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"  [재시도 {attempt+1}/{MAX_RETRIES}] {e}")
                time.sleep(RETRY_DELAY)
            else:
                return {"_error": str(e), "_raw": ""}, last_usage


def run(pairs: list[tuple[int, str]], reset: bool):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    x_text = DATA_PATH.read_text(encoding="utf-8")
    preamble = load_preamble()
    client = anthropic.Anthropic()

    total = len(pairs)
    done = skipped = errors = 0
    total_in = total_out = 0
    t_start = time.time()

    for i, (q_num, code) in enumerate(pairs, 1):
        label = f"Q{q_num:02d}_{code}"
        out_path = RESULT_DIR / f"{label}.json"
        err_path = RESULT_DIR / f"{label}_ERROR.json"

        if not reset and (out_path.exists() or err_path.exists()):
            print(f"[{i:3d}/{total}] {label} — 스킵")
            skipped += 1
            continue

        print(f"[{i:3d}/{total}] {label} ...", end=" ", flush=True)
        t0 = time.time()

        try:
            type_prompt = load_type_prompt(code)
            question_block = extract_question(x_text, q_num)
            user_content = build_user_content(type_prompt, question_block)
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

        result, usage = call_with_retry(client, preamble, user_content)
        elapsed = time.time() - t0
        total_in += usage.get("input_tokens", 0)
        total_out += usage.get("output_tokens", 0)

        if result and "_error" in result:
            err_path.write_text(
                json.dumps({"question_number": q_num, "type_code": code,
                            "_error": result["_error"],
                            "_raw": result.get("_raw", ""),
                            "found": None},
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
            conf = result.get("confidence", "?")
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            print(f"{'found' if found else 'none ':5s}  conf={conf}  ({elapsed:.1f}s, in={in_tok} out={out_tok})")
            done += 1

    elapsed_total = time.time() - t_start
    # Haiku 4.5: $1/M in, $5/M out
    cost = total_in / 1_000_000 * 1.0 + total_out / 1_000_000 * 5.0
    print(f"\n[완료] 성공={done}  스킵={skipped}  에러={errors}  합계={total}")
    print(f"[토큰] in={total_in}  out={total_out}  (예상 비용 ${cost:.4f})")
    print(f"[시간] {elapsed_total:.1f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="dry_run 5쌍만 실행")
    parser.add_argument("--q", type=int, help="특정 문항 번호만 실행")
    parser.add_argument("--type", type=str, help="특정 유형 코드만 실행 (예: A09)")
    parser.add_argument("--reset", action="store_true", help="기존 결과 무시하고 재실행")
    args = parser.parse_args()

    if args.dry:
        pairs = [(q, code) for code, q in DRY_RUN_PAIRS]
    else:
        type_filter = args.type.upper() if args.type else None
        pairs = [
            (q, code)
            for q in ALL_QUESTIONS
            for code in ALL_TYPES
            if (args.q is None or q == args.q)
            and (type_filter is None or code == type_filter)
        ]

    run(pairs, reset=args.reset)


if __name__ == "__main__":
    main()
