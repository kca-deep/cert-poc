"""
dry_run.py — 시범 5개 유형 × 대응 문항 LM Studio 호출 테스트

사용법:
    python src/dry_run.py                    # 기본: A01~Q1, A02~Q2, A04~Q4, A06~Q6, A14~Q14
    python src/dry_run.py --type A01 --q 1   # 특정 유형+문항만
    python src/dry_run.py --all              # 5개 쌍 전체

출력: results/dry_run/A{nn}_Q{n}.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows cp949 콘솔 한글 깨짐 방지
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

# 시범 5개: (유형코드, 대응 문항 번호)
DRY_RUN_PAIRS = [
    ("A01", 1),
    ("A02", 2),
    ("A04", 4),
    ("A06", 6),
    ("A14", 14),
]

PROMPT_DIR  = ROOT / "prompts"
DATA_PATH   = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR  = ROOT / "results" / "dry_run"


def load_preamble() -> str:
    return (PROMPT_DIR / "_shared" / "system_preamble.md").read_text(encoding="utf-8")


def load_type_prompt(code: str) -> str:
    """per-type 디렉터리에서 코드가 일치하는 파일을 찾아 읽기."""
    matches = list((PROMPT_DIR / "per-type").glob(f"{code}_*.md"))
    if not matches:
        raise FileNotFoundError(f"프롬프트 파일 없음: {code}_*.md")
    return matches[0].read_text(encoding="utf-8")


def extract_question(md_text: str, n: int) -> str:
    """_X.md 에서 ## N. 헤더 단위로 문항 추출."""
    pattern = rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)"
    m = re.search(pattern, md_text)
    if not m:
        raise ValueError(f"문항 {n}번을 찾을 수 없습니다.")
    return m.group(1).strip()


def sanitize(text: str) -> str:
    """gpt-oss-20b 에서 '>' 블록쿼트가 degenerate 루프를 유발하므로 전처리로 제거."""
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
    """
    system : preamble (전역 규약)
    user   : type_prompt 의 {{QUESTION_BLOCK}} 을 실제 문항으로 치환한 전체 내용
    """
    clean_prompt = sanitize(type_prompt)
    clean_question = sanitize(question_block)
    user_content = clean_prompt.replace("{{QUESTION_BLOCK}}", clean_question)
    return [
        {"role": "system", "content": preamble},
        {"role": "user",   "content": user_content},
    ]


class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_lm_studio(messages: list[dict]) -> dict:
    # max_retries=0: OpenAI 클라이언트 내부 자동 재시도 비활성화 (degenerate loop 시 9회→1회)
    # timeout=90: HTTP 응답 최대 대기 90초
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
    rt = resp.usage.completion_tokens_details.reasoning_tokens if resp.usage.completion_tokens_details else "?"
    # 코드펜스 제거 (모델이 감쌀 경우 대비)
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise LMCallError(
            f"JSON 파싱 실패 (finish={finish}, reasoning_tokens={rt}): {e}",
            raw=raw[:1000]
        )


def run_pair(code: str, q_num: int, x_text: str, preamble: str, verbose: bool = True):
    print(f"\n{'='*60}")
    print(f"[{code}] Q{q_num}")
    print(f"{'='*60}")

    type_prompt   = load_type_prompt(code)
    question_block = extract_question(x_text, q_num)

    if verbose:
        print(f"[문항 미리보기]\n{question_block[:200]}{'...' if len(question_block)>200 else ''}\n")

    messages = build_messages(preamble, type_prompt, question_block)

    try:
        result = call_lm_studio(messages)
    except LMCallError as e:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        raw_path = RESULT_DIR / f"{code}_Q{q_num:02d}_RAW.txt"
        raw_path.write_text(e.raw, encoding="utf-8")
        print(f"[오류] {e}")
        print(f"[RAW (첫 500자)] {e.raw[:500]!r}")
        return None
    except Exception as e:
        print(f"[오류] 호출 실패: {e}")
        return None

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 저장
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULT_DIR / f"{code}_Q{q_num:02d}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ 저장: {out_path}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", help="유형 코드 (예: A01)")
    parser.add_argument("--q",   type=int, help="문항 번호")
    parser.add_argument("--all", action="store_true", help="기본 5개 쌍 전체 실행")
    args = parser.parse_args()

    x_text  = DATA_PATH.read_text(encoding="utf-8")
    preamble = load_preamble()

    if args.type and args.q:
        run_pair(args.type.upper(), args.q, x_text, preamble)
    else:
        # --all 또는 인자 없음 → 기본 5개 쌍
        for code, q_num in DRY_RUN_PAIRS:
            run_pair(code, q_num, x_text, preamble)

    print("\n[완료] dry-run 종료")


if __name__ == "__main__":
    main()
