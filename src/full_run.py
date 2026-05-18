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
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("openai 패키지가 필요합니다: pip install openai")

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

BASE_URL = os.getenv("LOCAL_BASE_URL", "http://127.0.0.1:1234/v1")
MODEL    = "openai/gpt-oss-20b"   # 축약형 'gpt-oss-20b'는 깨진 참조 (garbage 출력)

ALL_TYPES = [f"A{n:02d}" for n in range(1, 21)]
ALL_QUESTIONS = list(range(1, 21))

PROMPT_DIR  = ROOT / "prompts"
DATA_PATH   = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR  = ROOT / "results" / "full_run"

MAX_RETRIES = 1     # 우리 래퍼 재시도 횟수 (총 2회 시도)
RETRY_DELAY = 5     # 서버 회복 대기 (초)


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


def call_lm_studio(messages: list[dict]) -> dict:
    # max_retries=0: OpenAI 클라이언트 내부 자동 재시도 비활성화 (우리 래퍼가 담당)
    # timeout=120: HTTP 응답 최대 대기 120초
    client = OpenAI(base_url=BASE_URL, api_key="lm-studio", timeout=120, max_retries=0)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=1.0,
        max_tokens=16000,
        extra_body={"reasoning_effort": "medium"},   # 'high' → 'medium': timeout/품질 균형
    )
    raw = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    rt = (resp.usage.completion_tokens_details.reasoning_tokens
          if resp.usage and resp.usage.completion_tokens_details else "?")
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise LMCallError(
            f"JSON 파싱 실패 (finish={finish}, reasoning_tokens={rt}): {e}",
            raw=raw[:2000],
        )


def call_with_retry(messages: list[dict], label: str) -> dict | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            return call_lm_studio(messages)
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

        result = call_with_retry(messages, label)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--q",    type=int,  help="특정 문항 번호만 실행")
    parser.add_argument("--type", type=str,  help="특정 유형 코드만 실행 (예: A09)")
    parser.add_argument("--reset", action="store_true", help="기존 결과 무시하고 재실행")
    args = parser.parse_args()

    type_filter = args.type.upper() if args.type else None
    run_all(q_filter=args.q, type_filter=type_filter, reset=args.reset)


if __name__ == "__main__":
    main()
