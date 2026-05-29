"""
hybrid_run.py — 3레이어 하이브리드 파이프라인

Layer 0 (코드, 0 LLM): A01, A03, A13, A15, A17, A18
Layer 1 (그룹 LLM, 90호출): G1[A04,A05,A06] / G4[A09,A20] / G5[A11,A14]
Layer 2 (per-type LLM, 210호출): A02, A07, A08, A10, A12, A16, A19

사용법:
    python src/hybrid_run.py --input data/파일.md
    python src/hybrid_run.py --input data/파일.md --q 13
    python src/hybrid_run.py --input data/파일.md --reset
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
from code_checker import run_code_check, extract_all_questions
from postprocess import run as run_postprocess

ROOT       = Path(__file__).parent.parent
PROMPT_DIR = ROOT / "prompts"
DATA_PATH  = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR = ROOT / "results" / "hybrid"

CFG         = lm_config()
BASE_URL    = CFG["base_url"]
MODEL       = CFG["model"]
MAX_RETRIES = CFG["max_retries"]
RETRY_DELAY = CFG["retry_delay"]

# ── 레이어 정의 ───────────────────────────────────────────────

LAYER0_TYPES = {"A01", "A03", "A13", "A15", "A17", "A18"}

LAYER1_GROUPS = [
    {"code": "G1", "file": "hybrid/G1_typo_spelling.md",  "types": ["A04", "A05", "A06"]},
    {"code": "G4", "file": "hybrid/G4_legal_domain.md",   "types": ["A09", "A20"]},
    {"code": "G5", "file": "hybrid/G5_editorial.md",      "types": ["A11", "A14"]},
]

LAYER2_TYPES = ["A02", "A07", "A08", "A10", "A12", "A16", "A19", "A21"]


# ── 공통 유틸 ─────────────────────────────────────────────────

def extract_question(md_text: str, n: int) -> str:
    m = re.search(rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)", md_text)
    if not m:
        raise ValueError(f"문항 {n}번을 찾을 수 없습니다.")
    return m.group(1).strip()


def extract_all_question_numbers(md_text: str) -> list[int]:
    return sorted(int(m) for m in re.findall(r"^## (\d+)\.", md_text, re.MULTILINE))


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


def load_prompt(rel_path: str) -> str:
    return (PROMPT_DIR / rel_path).read_text(encoding="utf-8")


def load_preamble() -> str:
    return (PROMPT_DIR / "_shared" / "system_preamble.md").read_text(encoding="utf-8")


def load_pertype_prompt(code: str) -> str:
    matches = list((PROMPT_DIR / "per-type").glob(f"{code}_*.md"))
    if not matches:
        raise FileNotFoundError(f"per-type 프롬프트 없음: {code}_*.md")
    return matches[0].read_text(encoding="utf-8")


# ── LLM 호출 ──────────────────────────────────────────────────

class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_lm_studio(messages: list[dict], slot_id: int = -1) -> dict:
    client = OpenAI(base_url=BASE_URL, api_key="lm-studio",
                    timeout=CFG["timeout"], max_retries=0)
    extra: dict = {
        "reasoning_effort": CFG["reasoning_effort"],
        "cache_prompt": CFG.get("cache_prompt", False),
    }
    if slot_id >= 0:
        extra["slot_id"] = slot_id
    resp = client.chat.completions.create(
        model=MODEL, messages=messages,
        temperature=CFG["temperature"], max_tokens=CFG["max_tokens"],
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
            f"JSON 파싱 실패 (finish={finish}): {last_error or e}", raw=raw[:2000]
        )


def call_with_retry(messages: list[dict], label: str, slot_id: int = -1) -> dict | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            return call_lm_studio(messages, slot_id=slot_id)
        except LMCallError as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return {"_error": str(e), "_raw": e.raw}
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                return {"_error": str(e), "_raw": ""}


# ── 저장 헬퍼 ─────────────────────────────────────────────────

def save(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def already_done(result_dir: Path, label: str) -> bool:
    return (result_dir / f"{label}.json").exists() or \
           (result_dir / f"{label}_ERROR.json").exists()


# ── Layer 0 실행 ──────────────────────────────────────────────

def run_layer0(md_path: Path, result_dir: Path, q_filter: int | None, reset: bool):
    print("\n[Layer 0] 코드 기반 탐지 (A01·A03·A13·A15·A17·A18)")
    layer_dir = result_dir / "layer0"
    layer_dir.mkdir(parents=True, exist_ok=True)

    if reset:
        pattern = f"Q{q_filter:02d}_*.json" if q_filter else "*.json"
        for f in layer_dir.glob(pattern):
            f.unlink()

    results = run_code_check(md_path, q_filter=q_filter, output_dir=layer_dir)
    found = sum(1 for r in results if r.get("found"))
    print(f"  → {len(results)}건 검사, found={found}")
    return results


# ── Layer 1 실행 ──────────────────────────────────────────────

def run_layer1(md_text: str, questions: list[int], result_dir: Path,
               q_filter: int | None, reset: bool, preamble: str):
    print("\n[Layer 1] 그룹 LLM (G1·G4·G5)")
    layer_dir = result_dir / "layer1"
    layer_dir.mkdir(parents=True, exist_ok=True)

    if reset and q_filter:
        for f in layer_dir.glob(f"Q{q_filter:02d}_*.json"):
            f.unlink()

    pairs = [(q, g) for q in questions for g in LAYER1_GROUPS
             if q_filter is None or q == q_filter]
    total = len(pairs)
    done = skipped = errors = 0

    for i, (q_num, grp) in enumerate(pairs, 1):
        label = f"Q{q_num:02d}_{grp['code']}"
        if not reset and already_done(layer_dir, label):
            skipped += 1
            continue

        print(f"  [{i:3d}/{total}] {label} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            prompt  = load_prompt(grp["file"])
            qblock  = extract_question(md_text, q_num)
            content = sanitize(prompt).replace("{{QUESTION_BLOCK}}", sanitize(qblock))
            msgs    = [{"role": "system", "content": preamble},
                       {"role": "user",   "content": content}]
        except Exception as e:
            print(f"준비 실패: {e}")
            save(layer_dir / f"{label}_ERROR.json",
                 {"question_number": q_num, "group_code": grp["code"], "_error": str(e)})
            errors += 1
            continue

        n_slots = CFG.get("n_slots", 4)
        slot_id = (i - 1) % n_slots if CFG.get("slot_round_robin", False) else -1
        result  = call_with_retry(msgs, label, slot_id=slot_id)
        elapsed = time.time() - t0

        if result and "_error" in result:
            save(layer_dir / f"{label}_ERROR.json",
                 {"question_number": q_num, "group_code": grp["code"],
                  "_error": result["_error"], "_raw": result.get("_raw", "")})
            print(f"에러 ({elapsed:.1f}s)")
            errors += 1
        else:
            save(layer_dir / f"{label}.json", result)
            found_types = [r["type_code"] for r in result.get("results", [])
                           if r.get("found")]
            tag = f"found={','.join(found_types)}" if found_types else "none"
            print(f"{tag}  ({elapsed:.1f}s)")
            done += 1

    print(f"  → 성공={done} 스킵={skipped} 에러={errors}")


# ── Layer 2 실행 ──────────────────────────────────────────────

def run_layer2(md_text: str, questions: list[int], result_dir: Path,
               q_filter: int | None, reset: bool, preamble: str):
    print("\n[Layer 2] per-type LLM (A02·A07·A08·A10·A12·A16·A19·A21)")
    layer_dir = result_dir / "layer2"
    layer_dir.mkdir(parents=True, exist_ok=True)

    if reset and q_filter:
        for f in layer_dir.glob(f"Q{q_filter:02d}_*.json"):
            f.unlink()

    pairs = [(q, t) for q in questions for t in LAYER2_TYPES
             if q_filter is None or q == q_filter]
    total = len(pairs)
    done = skipped = errors = 0

    for i, (q_num, type_code) in enumerate(pairs, 1):
        label = f"Q{q_num:02d}_{type_code}"
        if not reset and already_done(layer_dir, label):
            skipped += 1
            continue

        print(f"  [{i:3d}/{total}] {label} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            prompt  = load_pertype_prompt(type_code)
            qblock  = extract_question(md_text, q_num)
            content = sanitize(prompt).replace("{{QUESTION_BLOCK}}", sanitize(qblock))
            msgs    = [{"role": "system", "content": preamble},
                       {"role": "user",   "content": content}]
        except Exception as e:
            print(f"준비 실패: {e}")
            save(layer_dir / f"{label}_ERROR.json",
                 {"question_number": q_num, "type_code": type_code, "_error": str(e)})
            errors += 1
            continue

        n_slots = CFG.get("n_slots", 4)
        slot_id = (i - 1) % n_slots if CFG.get("slot_round_robin", False) else -1
        result  = call_with_retry(msgs, label, slot_id=slot_id)
        elapsed = time.time() - t0

        if result and "_error" in result:
            save(layer_dir / f"{label}_ERROR.json",
                 {"question_number": q_num, "type_code": type_code,
                  "_error": result["_error"], "_raw": result.get("_raw", "")})
            print(f"에러 ({elapsed:.1f}s)")
            errors += 1
        else:
            save(layer_dir / f"{label}.json", result)
            found = result.get("found", False)
            conf  = result.get("confidence", "")
            tag   = "found" if found else "none "
            print(f"{tag}  conf={conf}  ({elapsed:.1f}s)")
            done += 1

    print(f"  → 성공={done} 스킵={skipped} 에러={errors}")


# ── 결과 병합 및 요약 ─────────────────────────────────────────

def merge_and_summarize(result_dir: Path, questions: list[int]):
    print("\n[결과 병합]")
    merged: dict[int, dict[str, dict]] = {int(q): {} for q in questions}

    # Layer 0
    for f in (result_dir / "layer0").glob("Q*_A*.json"):
        if "_ERROR" in f.name:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        q, t = r.get("question_number"), r.get("type_code")
        if q and t:
            merged.setdefault(int(q), {})[t] = r

    # Layer 1 (그룹 → 개별 유형으로 펼치기)
    for f in (result_dir / "layer1").glob("Q*_G*.json"):
        if "_ERROR" in f.name:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        q = r.get("question_number")
        for sub in r.get("results", []):
            t = sub.get("type_code")
            if q and t:
                merged.setdefault(int(q), {})[t] = sub

    # Layer 2
    for f in (result_dir / "layer2").glob("Q*_A*.json"):
        if "_ERROR" in f.name:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        q, t = r.get("question_number"), r.get("type_code")
        if q and t:
            merged.setdefault(int(q), {})[t] = r

    # 병합 결과 저장
    merged_path = result_dir / "merged.json"
    merged_out  = {str(q): v for q, v in sorted(merged.items())}
    merged_path.write_text(json.dumps(merged_out, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    # 요약 출력
    print(f"\n{'='*60}")
    print("  Hybrid Pipeline 탐지 결과 요약")
    print(f"{'='*60}")

    all_found: dict[int, list[str]] = {}
    for q in sorted(merged):
        found_types = sorted(t for t, r in merged[q].items()
                             if r.get("found") is True)
        if found_types:
            all_found[q] = found_types

    if all_found:
        print(f"\n{'Q':>4}  {'탐지 유형':<40} 레이어")
        print(f"  {'-'*55}")
        for q, types in sorted(all_found.items()):
            for t in types:
                r    = merged[q][t]
                layer = r.get("layer", "L2" if "type_code" in r else "?")
                method = r.get("method", "llm")
                layer_tag = f"L{layer}(코드)" if method == "code" else f"L{layer}(LLM)"
                issue = ""
                issues = r.get("issues", [])
                if issues:
                    issue = issues[0].get("original", "")[:40]
                print(f"  Q{q:02d}  {t:<6} {issue:<40} {layer_tag}")
    else:
        print("  탐지된 이상 없음")

    total_found = sum(len(v) for v in all_found.values())
    print(f"\n  탐지 문항: {len(all_found)}개 / {len(questions)}문항")
    print(f"  탐지 건수: {total_found}건")
    print(f"  결과 저장: {merged_path}")
    return merged


# ── 메인 ──────────────────────────────────────────────────────

def main():
    global RESULT_DIR, DATA_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  type=str, default=None)
    parser.add_argument("--q",      type=int, default=None)
    parser.add_argument("--reset",  action="store_true")
    parser.add_argument("--outdir", type=str, default=None)
    args = parser.parse_args()

    if args.input:
        DATA_PATH = Path(args.input)
    if args.outdir:
        RESULT_DIR = Path(args.outdir)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    print_lm_config(CFG)
    print(f"입력: {DATA_PATH.name}")
    print(f"출력: {RESULT_DIR}")

    md_text   = DATA_PATH.read_text(encoding="utf-8")
    questions = extract_all_question_numbers(md_text)
    preamble  = load_preamble()

    t_start = time.time()
    run_layer0(DATA_PATH, RESULT_DIR, args.q, args.reset)
    run_layer1(md_text, questions, RESULT_DIR, args.q, args.reset, preamble)
    run_layer2(md_text, questions, RESULT_DIR, args.q, args.reset, preamble)
    merge_and_summarize(RESULT_DIR, questions)
    print("\n[후처리 필터 적용]")
    run_postprocess(RESULT_DIR)
    print(f"\n총 소요 시간: {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
