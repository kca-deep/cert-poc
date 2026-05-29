"""
postprocess.py — hybrid 결과 후처리 필터

탐지된 issues 중 알려진 오탐 패턴을 제거합니다.
merged.json을 읽어 필터 적용 후 merged_filtered.json으로 저장합니다.

필터 규칙:
  F1. A06 오탐: 같은 문항에서 A02도 탐지된 경우 — 오자를 띄어쓰기 오류로 오분류
  F2. A11 중복: 같은 문항에서 A12도 탐지된 경우 — A12(복수 메모)가 우선
  F3. 파이프 문자: A06의 original에 | 포함 — MD 파싱 아티팩트
  F4. A02 의미 오류: suspected에 "의미" "문맥" "사전에 있는" 포함 — 사전 등재어 오분류
  F5. A02/A16/A08/A10 원형 보존 단어: original의 핵심 단어가 교정어(suggested)와
      음절 공유 없는 경우 — 자모 오자가 아닌 의미 교체를 오탐
"""

import json
import re
from pathlib import Path


# ── 필터 함수 ─────────────────────────────────────────────────

def _get_original_words(issues: list) -> set[str]:
    """issues에서 핵심 단어(따옴표로 감싸진 첫 번째 단어) 추출."""
    words = set()
    for iss in issues:
        orig = iss.get("original", "")
        # 1~3글자 한글 단어 추출
        for w in re.findall(r"[가-힣]{1,4}", orig):
            words.add(w)
    return words


def _char_overlap(w1: str, w2: str) -> bool:
    """두 단어 사이에 공유 음절이 있으면 True."""
    return bool(set(w1) & set(w2))


def _extract_key_word(text: str) -> str:
    """suspected/original에서 따옴표 안 첫 단어 추출."""
    m = re.search(r"'([^']+)'", text)
    return m.group(1) if m else ""


def filter_f1_a06_when_a02(q_results: dict) -> dict:
    """F1: 같은 문항에서 A02와 A06이 모두 found:true → A06 제거."""
    a02 = q_results.get("A02", {})
    a06 = q_results.get("A06", {})
    if not (a02.get("found") and a06.get("found")):
        return q_results

    # A02와 A06의 original이 겹치면 A06는 오탐
    a02_words = _get_original_words(a02.get("issues", []))
    a06_words = _get_original_words(a06.get("issues", []))
    if a02_words & a06_words:
        q_results = dict(q_results)
        q_results["A06"] = {**a06, "found": False, "issues": [],
                            "_filtered": "F1: A02와 동일 위치 — 오자를 띄어쓰기 오류로 오분류"}
    return q_results


def filter_f2_a11_when_a12(q_results: dict) -> dict:
    """F2: 같은 문항에서 A12도 found:true면 A11 제거 (A12가 우선)."""
    a11 = q_results.get("A11", {})
    a12 = q_results.get("A12", {})
    if a11.get("found") and a12.get("found"):
        q_results = dict(q_results)
        q_results["A11"] = {**a11, "found": False, "issues": [],
                            "_filtered": "F2: A12(복수 메모)와 동일 위치 — A11 중복 탐지"}
    return q_results


def filter_f3_pipe_char(q_results: dict) -> dict:
    """F3: A06 original에 | 포함 → MD 파싱 아티팩트."""
    a06 = q_results.get("A06", {})
    if not a06.get("found"):
        return q_results
    for iss in a06.get("issues", []):
        if "|" in iss.get("original", ""):
            q_results = dict(q_results)
            q_results["A06"] = {**a06, "found": False, "issues": [],
                                "_filtered": "F3: | 기호 — MD 파싱 아티팩트"}
            break
    return q_results


def filter_f4_a02_semantic(q_results: dict) -> dict:
    """F4: A02의 suspected에 의미 판단 키워드 포함 → 사전 등재어 오분류."""
    a02 = q_results.get("A02", {})
    if not a02.get("found"):
        return q_results
    SEMANTIC_KEYWORDS = ["의미상", "문맥상", "문맥", "표준국어대사전에 있는", "사전에 있는"]
    for iss in a02.get("issues", []):
        susp = iss.get("suspected", "")
        if any(kw in susp for kw in SEMANTIC_KEYWORDS):
            q_results = dict(q_results)
            q_results["A02"] = {**a02, "found": False, "issues": [],
                                "_filtered": "F4: A02 의미 판단 — 사전 등재어 오분류"}
            break
    return q_results


def filter_f5_no_char_overlap(q_results: dict) -> dict:
    """F5: A02/A16에서 original 단어와 suggested 단어 간 음절 공유 없음 → 의미 교체 오탐.
    A08(문장 구조)·A10(복합)은 제외 — 문장 단위 탐지라 음절 유사도 기준 부적합."""
    TARGETS = ["A02", "A16"]
    updated = dict(q_results)
    for t in TARGETS:
        r = updated.get(t, {})
        if not r.get("found"):
            continue
        for iss in r.get("issues", []):
            orig_word = _extract_key_word(iss.get("suspected", ""))
            sugg      = iss.get("suggested") or ""
            sugg_word = re.sub(r"[^가-힣]", "", sugg)[:4]  # 앞 4글자
            if orig_word and sugg_word and not _char_overlap(orig_word, sugg_word):
                updated[t] = {**r, "found": False, "issues": [],
                              "_filtered": f"F5: '{orig_word}'↔'{sugg_word}' 음절 공유 없음 — 의미 교체 오탐"}
                break
    return updated


ALL_FILTERS = [
    filter_f3_pipe_char,    # 파이프 먼저 (빠름)
    filter_f4_a02_semantic,
    filter_f5_no_char_overlap,
    filter_f1_a06_when_a02, # A02 필터 이후에 실행
    filter_f2_a11_when_a12,
]


# ── 메인 적용 ─────────────────────────────────────────────────

def apply_filters(merged: dict) -> tuple[dict, list]:
    """
    merged.json 구조 {q_str: {type_code: result}} 에 필터 적용.
    반환: (filtered_merged, filter_log)
    """
    filter_log = []
    filtered = {}

    for q_str, q_results in merged.items():
        updated = dict(q_results)
        for fn in ALL_FILTERS:
            before = {t: r.get("found") for t, r in updated.items()}
            updated = fn(updated)
            after  = {t: r.get("found") for t, r in updated.items()}
            for t in before:
                if before[t] and not after[t]:
                    reason = updated[t].get("_filtered", fn.__name__)
                    filter_log.append((int(q_str), t, reason))
        filtered[q_str] = updated

    return filtered, filter_log


def run(result_dir: Path):
    merged_path   = result_dir / "merged.json"
    filtered_path = result_dir / "merged_filtered.json"

    if not merged_path.exists():
        print(f"merged.json 없음: {merged_path}")
        return

    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    filtered, log = apply_filters(merged)

    filtered_path.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[postprocess] 필터 적용: {len(log)}건 제거")
    for q, t, reason in sorted(log):
        print(f"  Q{q:02d}-{t}  {reason}")
    print(f"  저장: {filtered_path}")
    return filtered, log


if __name__ == "__main__":
    import sys
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/hybrid_v2")
    run(d)
