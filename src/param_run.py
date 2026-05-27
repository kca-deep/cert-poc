"""
param_run.py — 파라미터 조합 실험용 러너

CLI 인자를 지정하지 않으면 .env 값이 기본값으로 적용됩니다.

사용법:
    python src/param_run.py                          # .env 파라미터 그대로
    python src/param_run.py --questions 4 5 11 13    # 특정 문항만
    python src/param_run.py --temp 0.0 --effort medium --max 8000  # 개별 덮어쓰기
    python src/param_run.py --reset                  # 기존 결과 무시

결과: results/param_run/Q{nn}_{Axx}.json
"""

import argparse, json, re, sys, time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8","utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("openai 패키지 필요: pip install openai")

from config import lm_config, print_lm_config

ROOT = Path(__file__).parent.parent

ALL_TYPES     = [f"A{n:02d}" for n in range(1, 21)]
ALL_QUESTIONS = list(range(1, 21))

PROMPT_DIR = ROOT / "prompts"
DATA_PATH  = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR = ROOT / "results" / "param_run"


def load_preamble(): return (PROMPT_DIR / "_shared" / "system_preamble.md").read_text(encoding="utf-8")

def load_type_prompt(code):
    matches = list((PROMPT_DIR / "per-type").glob(f"{code}_*.md"))
    if not matches: raise FileNotFoundError(f"프롬프트 없음: {code}")
    return matches[0].read_text(encoding="utf-8")

def extract_question(md_text, n):
    m = re.search(rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)", md_text)
    if not m: raise ValueError(f"문항 {n}번 없음")
    return m.group(1).strip()

def sanitize(text):
    lines = []
    for line in text.splitlines():
        if line.startswith("> "): lines.append("(지문) " + line[2:])
        elif line == ">":         lines.append("(지문)")
        else:                     lines.append(line)
    return "\n".join(lines)

def build_messages(preamble, type_prompt, question_block):
    user_content = sanitize(type_prompt).replace("{{QUESTION_BLOCK}}", sanitize(question_block))
    return [{"role":"system","content":preamble},{"role":"user","content":user_content}]

class LMCallError(Exception):
    def __init__(self, msg, raw=""):
        super().__init__(msg); self.raw = raw

def call_lm(messages, cfg):
    client = OpenAI(base_url=cfg["base_url"], api_key="lm-studio",
                    timeout=cfg["timeout"], max_retries=0)
    resp = client.chat.completions.create(
        model=cfg["model"], messages=messages,
        temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
        extra_body={"reasoning_effort": cfg["reasoning_effort"]},
    )
    raw = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    rt = (resp.usage.completion_tokens_details.reasoning_tokens
          if resp.usage and resp.usage.completion_tokens_details else "?")
    clean = re.sub(r"^```(?:json)?\s*","",raw); clean = re.sub(r"\s*```$","",clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise LMCallError(f"JSON파싱실패(finish={finish},rt={rt}):{e}", raw=raw[:2000])

def call_with_retry(messages, label, cfg):
    for attempt in range(cfg["max_retries"] + 1):
        try:
            return call_lm(messages, cfg)
        except LMCallError as e:
            if attempt < cfg["max_retries"]:
                print(f"  [재시도] {e}"); time.sleep(cfg["retry_delay"])
            else: return {"_error": str(e), "_raw": e.raw}
        except Exception as e:
            if attempt < cfg["max_retries"]:
                print(f"  [재시도] {e}"); time.sleep(cfg["retry_delay"])
            else: return {"_error": str(e), "_raw": ""}

def run_all(q_filter, reset, cfg, result_dir=None):
    out_dir = Path(result_dir) if result_dir else RESULT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    x_text   = DATA_PATH.read_text(encoding="utf-8")
    preamble = load_preamble()

    pairs = [(q,code) for q in ALL_QUESTIONS for code in ALL_TYPES
             if (q_filter is None or q in q_filter)]
    total = len(pairs)
    print(f"대상: {total}콜 ({len(set(q for q,_ in pairs))}문항 × 20유형)\n")

    done = skipped = errors = 0
    for i,(q_num,code) in enumerate(pairs,1):
        label    = f"Q{q_num:02d}_{code}"
        out_path = out_dir / f"{label}.json"
        err_path = out_dir / f"{label}_ERROR.json"

        if not reset and (out_path.exists() or err_path.exists()):
            print(f"[{i:3d}/{total}] {label} — 스킵"); skipped+=1; continue

        print(f"[{i:3d}/{total}] {label} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            type_prompt    = load_type_prompt(code)
            question_block = extract_question(x_text, q_num)
            messages       = build_messages(preamble, type_prompt, question_block)
        except Exception as e:
            print(f"준비실패: {e}")
            err_path.write_text(json.dumps({"question_number":q_num,"type_code":code,"_error":str(e),"found":None},ensure_ascii=False,indent=2),encoding="utf-8")
            errors+=1; continue

        result = call_with_retry(messages, label, cfg)
        elapsed = time.time()-t0

        if result and "_error" in result:
            err_path.write_text(json.dumps({"question_number":q_num,"type_code":code,"_error":result["_error"],"_raw":result.get("_raw",""),"found":None},ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"에러 ({elapsed:.1f}s)"); errors+=1
        else:
            out_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"{'found' if result.get('found') else 'none ':5s}  conf={result.get('confidence','?')}  ({elapsed:.1f}s)")
            done+=1

    print(f"\n[완료] 성공={done}  스킵={skipped}  에러={errors}  합계={total}")

def main():
    p = argparse.ArgumentParser(
        description="파라미터 실험 러너 — 미지정 항목은 .env 기본값 사용"
    )
    p.add_argument("--questions", nargs="+", type=int, help="대상 문항 번호 목록")
    p.add_argument("--temp",   type=float, default=None, help="temperature (.env 우선)")
    p.add_argument("--effort", type=str,   default=None, help="reasoning_effort (.env 우선)")
    p.add_argument("--max",    type=int,   default=None, help="max_tokens (.env 우선)")
    p.add_argument("--url",    type=str,   default=None, help="서버 base_url 오버라이드")
    p.add_argument("--model",  type=str,   default=None, help="모델 ID 오버라이드")
    p.add_argument("--outdir", type=str,   default=None, help="결과 저장 디렉토리 (기본: results/param_run)")
    p.add_argument("--reset",  action="store_true")
    args = p.parse_args()

    cfg = lm_config()
    overrides = {}
    if args.temp   is not None: cfg["temperature"],      overrides["temperature"]      = args.temp,   True
    if args.effort is not None: cfg["reasoning_effort"], overrides["reasoning_effort"] = args.effort, True
    if args.max    is not None: cfg["max_tokens"],       overrides["max_tokens"]       = args.max,    True
    if args.url    is not None: cfg["base_url"],         overrides["base_url"]         = args.url,    True
    if args.model  is not None: cfg["model"],            overrides["model"]            = args.model,  True

    print_lm_config(cfg, overrides)
    print()
    run_all(args.questions, args.reset, cfg, result_dir=args.outdir)

if __name__ == "__main__":
    main()
