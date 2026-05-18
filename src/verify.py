"""
verify.py — _O.md(정답본) vs _X.md(오류본) char-level diff + LLM 결과 검증

사용법:
    python src/verify.py                          # claude_haiku_run 검증 (기본)
    python src/verify.py --dir results/full_run   # gpt-oss-20b 검증
    python src/verify.py --diff-only              # diff만 추출 후 출력

산출물:
    results/diff_report.json  — Q_n 별 _O/_X char-level 변경 영역
    results/verify_<run>.json — (Q, A) × found/correct-location 판정 매트릭스
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
O_PATH = DATA_DIR / "정보보호개요_O.md"
X_PATH = DATA_DIR / "정보보호개요_X.md"

ALL_QUESTIONS = list(range(1, 21))
ALL_TYPES = [f"A{n:02d}" for n in range(1, 21)]

INJECTED_TYPE = {
    1: "A01", 2: "A02", 3: "A03", 4: "A04", 5: "A05",
    6: "A06", 7: "A07", 8: "A08", 9: "A09", 10: "A10",
    11: "A11", 12: "A12", 13: "A13", 14: "A14", 15: "A15",
    16: "A16", 17: "A17", 18: "A18", 19: "A19", 20: "A20",
}

TYPE_NAME = {
    "A01": "보기 중복", "A02": "오자", "A03": "보기개수 미달",
    "A04": "맞춤법", "A05": "오자(영어)", "A06": "띄어쓰기",
    "A07": "특수기호(?) 누락", "A08": "매끄럽지 못한 문장", "A09": "틀린 법령명",
    "A10": "오타+보기누락", "A11": "낙서(유형1)", "A12": "낙서(유형2)",
    "A13": "문항번호 중복", "A14": "정답유출", "A15": "보기 없음",
    "A16": "탈자", "A17": "원문자 탈자", "A18": "문장 전체 생략",
    "A19": "특수기호 누락(지문)", "A20": "틀린 법령 조항",
}


def extract_question(md_text: str, n: int) -> str:
    pattern = rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)"
    m = re.search(pattern, md_text)
    return m.group(1).strip() if m else ""


def char_diff(o_text: str, x_text: str) -> list[dict]:
    """char-level opcode 추출. 변경된 부분만 반환."""
    sm = difflib.SequenceMatcher(None, o_text, x_text, autojunk=False)
    spans = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        spans.append({
            "op": tag,         # 'replace' | 'delete' | 'insert'
            "o_text": o_text[i1:i2],
            "x_text": x_text[j1:j2],
            "o_pos": [i1, i2],
            "x_pos": [j1, j2],
        })
    return spans


def is_visually_identical(o_text: str, x_text: str) -> bool:
    """공백·줄바꿈만 다르면 True (정말 비어 있는 diff인지 판정)."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    return norm(o_text) == norm(x_text)


def build_diff_report() -> dict:
    o_text = O_PATH.read_text(encoding="utf-8")
    x_text = X_PATH.read_text(encoding="utf-8")
    report = {}
    for n in ALL_QUESTIONS:
        o_q = extract_question(o_text, n)
        x_q = extract_question(x_text, n)
        spans = char_diff(o_q, x_q)
        # X 측에 추가/변경된 텍스트 모음 (LLM이 찾아야 할 "원본")
        injected_strings = [s["x_text"] for s in spans if s["x_text"]]
        deleted_strings = [s["o_text"] for s in spans if s["o_text"] and s["op"] == "delete"]
        report[n] = {
            "spans": spans,
            "injected_strings": injected_strings,
            "deleted_strings": deleted_strings,
            "no_diff": len(spans) == 0,
            "visually_identical": is_visually_identical(o_q, x_q) and len(spans) > 0,
            "o_question": o_q,
            "x_question": x_q,
        }
    return report


def overlap_score(needle: str, haystack_list: list[str]) -> float:
    """needle 이 haystack 중 어느 하나와 얼마나 겹치는지 (0~1, substring 또는 SequenceMatcher 비율)."""
    if not needle or not haystack_list:
        return 0.0
    needle = needle.strip()
    best = 0.0
    for hay in haystack_list:
        if not hay:
            continue
        # 1. 직접 substring (양방향)
        if needle in hay or hay in needle:
            return 1.0
        # 2. SequenceMatcher 비율
        r = difflib.SequenceMatcher(None, needle, hay).ratio()
        best = max(best, r)
    return best


def verify_results(result_dir: Path, diff_report: dict) -> dict:
    """LLM 결과 디렉터리를 읽어 검증 매트릭스를 구축."""
    summary = {
        "TP_strict": 0,  # 유형 일치 & 위치 맞음
        "TP_loose": 0,   # 유형 일치 & 위치 다름 (또는 diff 없는 문항)
        "FP": 0,         # 유형 불일치 & found=true
        "FN": 0,         # 유형 일치인데 found=false
        "TN": 0,         # 유형 불일치 & found=false
        "ERR": 0,
        "MISSING": 0,
    }
    details = []
    type_breakdown = {c: {"TP_strict": 0, "TP_loose": 0, "FP": 0, "FN": 0, "TN": 0, "ERR": 0} for c in ALL_TYPES}

    for q in ALL_QUESTIONS:
        for code in ALL_TYPES:
            label = f"Q{q:02d}_{code}"
            ok_path = result_dir / f"{label}.json"
            err_path = result_dir / f"{label}_ERROR.json"

            expected_type = INJECTED_TYPE[q] == code

            if ok_path.exists():
                try:
                    data = json.loads(ok_path.read_text(encoding="utf-8"))
                except Exception as e:
                    summary["ERR"] += 1
                    type_breakdown[code]["ERR"] += 1
                    details.append({"q": q, "type": code, "verdict": "ERR", "reason": f"load: {e}"})
                    continue

                found = data.get("found", False)
                conf = data.get("confidence", "?")
                issues = data.get("issues", [])

                if found and expected_type:
                    # TP — 위치 매칭 확인
                    injected = diff_report[q]["injected_strings"]
                    deleted = diff_report[q]["deleted_strings"]
                    has_diff = not diff_report[q]["no_diff"]

                    if not has_diff:
                        # _O와 _X 동일 → 정답 위치 자체가 없음
                        verdict = "TP_loose"
                        reason = "no_diff_ground_truth"
                    else:
                        max_score = 0.0
                        for iss in issues:
                            orig = iss.get("original", "") or ""
                            score = max(
                                overlap_score(orig, injected),
                                overlap_score(orig, deleted),
                            )
                            max_score = max(max_score, score)
                        if max_score >= 0.6:
                            verdict = "TP_strict"
                            reason = f"overlap={max_score:.2f}"
                        else:
                            verdict = "TP_loose"
                            reason = f"overlap={max_score:.2f} (wrong location)"

                    summary[verdict] += 1
                    type_breakdown[code][verdict] += 1
                    details.append({
                        "q": q, "type": code, "verdict": verdict, "reason": reason,
                        "conf": conf,
                        "llm_original": issues[0].get("original", "")[:80] if issues else "",
                    })
                elif found and not expected_type:
                    summary["FP"] += 1
                    type_breakdown[code]["FP"] += 1
                    details.append({
                        "q": q, "type": code, "verdict": "FP",
                        "conf": conf,
                        "llm_original": issues[0].get("original", "")[:80] if issues else "",
                    })
                elif not found and expected_type:
                    summary["FN"] += 1
                    type_breakdown[code]["FN"] += 1
                    details.append({"q": q, "type": code, "verdict": "FN", "conf": conf})
                else:
                    summary["TN"] += 1
                    type_breakdown[code]["TN"] += 1
            elif err_path.exists():
                summary["ERR"] += 1
                type_breakdown[code]["ERR"] += 1
                details.append({"q": q, "type": code, "verdict": "ERR"})
            else:
                summary["MISSING"] += 1
                details.append({"q": q, "type": code, "verdict": "MISSING"})

    # 메트릭
    valid = summary["TP_strict"] + summary["TP_loose"] + summary["FP"] + summary["FN"] + summary["TN"]
    tp_total = summary["TP_strict"] + summary["TP_loose"]
    precision = tp_total / (tp_total + summary["FP"]) if (tp_total + summary["FP"]) > 0 else 0.0
    recall = tp_total / (tp_total + summary["FN"]) if (tp_total + summary["FN"]) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    loc_acc = summary["TP_strict"] / tp_total if tp_total > 0 else 0.0
    accuracy = (summary["TP_strict"] + summary["TP_loose"] + summary["TN"]) / valid if valid > 0 else 0.0

    return {
        "summary": summary,
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "location_accuracy": round(loc_acc, 4),  # TP 중 정확한 위치를 잡은 비율
        },
        "type_breakdown": type_breakdown,
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="results/claude_haiku_run",
                        help="검증할 결과 디렉터리 (기본: claude_haiku_run)")
    parser.add_argument("--diff-only", action="store_true", help="diff 추출만 수행하고 출력")
    args = parser.parse_args()

    print("[1/2] _O.md vs _X.md char-level diff 추출 중...")
    diff_report = build_diff_report()

    out_diff = ROOT / "results" / "diff_report.json"
    out_diff.parent.mkdir(parents=True, exist_ok=True)
    out_diff.write_text(
        json.dumps(diff_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → {out_diff}")

    # diff 요약
    no_diff_qs = [q for q in ALL_QUESTIONS if diff_report[q]["no_diff"]]
    print(f"\n■ _O/_X diff 요약")
    for q in ALL_QUESTIONS:
        d = diff_report[q]
        inj_t = INJECTED_TYPE[q]
        if d["no_diff"]:
            mark = "⚠ NO DIFF"
        else:
            n_spans = len(d["spans"])
            sample = (d["injected_strings"][0] if d["injected_strings"] else d["deleted_strings"][0] if d["deleted_strings"] else "")[:40]
            mark = f"{n_spans} spans  e.g. {sample!r}"
        print(f"  Q{q:02d} (INJECTED={inj_t}/{TYPE_NAME[inj_t]:<18}) — {mark}")

    if no_diff_qs:
        print(f"\n⚠ INJECTED_TYPE 사전이 주장하는 오류 주입이 자동 diff에서 발견되지 않은 문항: {no_diff_qs}")
        print("  → 운영자 매뉴얼 매핑이 잘못되었거나, 미세한 invisible-character 차이일 수 있음.")

    if args.diff_only:
        return

    result_dir = ROOT / args.dir
    if not result_dir.exists():
        print(f"\n[중단] 결과 디렉터리 없음: {result_dir}")
        return

    print(f"\n[2/2] {result_dir.name} 검증 매트릭스 구축 중...")
    verify_report = verify_results(result_dir, diff_report)

    run_name = result_dir.name
    out_verify = ROOT / "results" / f"verify_{run_name}.json"
    out_verify.write_text(
        json.dumps(verify_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → {out_verify}")

    s = verify_report["summary"]
    m = verify_report["metrics"]
    print(f"\n■ 검증 결과 ({run_name})")
    print(f"  TP-strict(정확 위치)     : {s['TP_strict']:3d}")
    print(f"  TP-loose(유형만 일치)    : {s['TP_loose']:3d}")
    print(f"  FP(환각)                : {s['FP']:3d}")
    print(f"  FN(미탐)                : {s['FN']:3d}")
    print(f"  TN(정상 음성)            : {s['TN']:3d}")
    print(f"  ERR/MISSING             : {s['ERR']}/{s['MISSING']}")
    print(f"  Precision               : {m['precision']:.3f}")
    print(f"  Recall                  : {m['recall']:.3f}")
    print(f"  F1                      : {m['f1']:.3f}")
    print(f"  Accuracy                : {m['accuracy']:.3f}")
    print(f"  Location Accuracy       : {m['location_accuracy']:.3f}  (TP 중 정확 위치를 잡은 비율)")


if __name__ == "__main__":
    main()
