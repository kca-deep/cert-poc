"""
analyze.py — full_run 결과를 로드해 정확도·오탐율 분석

사용법:
    python src/analyze.py                   # 전체 분석
    python src/analyze.py --detail          # 문항별·유형별 상세 출력
    python src/analyze.py --fp              # 오탐 목록만 출력

출력: 콘솔 + results/analysis.json
"""

import argparse
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT       = Path(__file__).parent.parent
RESULT_DIR = ROOT / "results" / "full_run"

ALL_TYPES     = [f"A{n:02d}" for n in range(1, 21)]
ALL_QUESTIONS = list(range(1, 21))

# Q_n 에 실제로 주입된 오류 유형 (Ground Truth)
INJECTED_TYPE = {
    1:  "A01",  # 보기 중복
    2:  "A02",  # 오자
    3:  "A03",  # 보기개수 미달
    4:  "A04",  # 맞춤법
    5:  "A05",  # 오자(영어)
    6:  "A06",  # 띄어쓰기
    7:  "A07",  # 특수기호 누락
    8:  "A08",  # 매끄럽지 못한 문장
    9:  "A09",  # 틀린 법령명
    10: "A10",  # 오타+보기누락
    11: "A11",  # 낙서 유형1
    12: "A12",  # 낙서 유형2
    13: "A13",  # 문항번호 중복
    14: "A14",  # 정답유출
    15: "A15",  # 보기 없음
    16: "A16",  # 탈자
    17: "A17",  # 원문자 탈자
    18: "A18",  # 문장 전체 생략
    19: "A19",  # 특수기호 누락(지문)
    20: "A20",  # 틀린 법령 조항
}

TYPE_NAME = {
    "A01": "보기 중복",      "A02": "오자",         "A03": "보기개수 미달",
    "A04": "맞춤법",          "A05": "오자(영어)",   "A06": "띄어쓰기",
    "A07": "특수기호(?) 누락","A08": "매끄럽지 못한 문장","A09": "틀린 법령명",
    "A10": "오타+보기누락",   "A11": "낙서(유형1)",  "A12": "낙서(유형2)",
    "A13": "문항번호 중복",   "A14": "정답유출",     "A15": "보기 없음",
    "A16": "탈자",            "A17": "원문자 탈자",  "A18": "문장 전체 생략",
    "A19": "특수기호 누락(지문)","A20": "틀린 법령 조항",
}

# Q_n × A0m 에서 A0m ≠ 주입 유형이지만 오탐으로 보지 않는 허용 쌍
# (A10은 A02·A15 조건을 포함하므로 일부 크로스 발화는 허용)
ALLOWED_CROSS = {
    (10, "A02"),  # Q10 오타 → A02도 true 가능
    (10, "A15"),  # Q10 보기누락 → A15도 true 가능
    (13, "A03"),  # Q13 번호중복 → A03도 true 가능 (실질적 보기 순서 불완전)
}


def expected(q_num: int, code: str) -> bool:
    """해당 (문항, 유형) 쌍의 기대 found 값."""
    if INJECTED_TYPE.get(q_num) == code:
        return True
    if (q_num, code) in ALLOWED_CROSS:
        return True   # 허용 크로스는 true 여도 정탐으로 처리
    return False


def load_results() -> list[dict]:
    records = []
    for q in ALL_QUESTIONS:
        for code in ALL_TYPES:
            label    = f"Q{q:02d}_{code}"
            ok_path  = RESULT_DIR / f"{label}.json"
            err_path = RESULT_DIR / f"{label}_ERROR.json"
            if ok_path.exists():
                try:
                    data = json.loads(ok_path.read_text(encoding="utf-8"))
                    records.append({
                        "q": q, "code": code,
                        "found": data.get("found"),
                        "confidence": data.get("confidence", "?"),
                        "issues": data.get("issues", []),
                        "error": None,
                    })
                except Exception as e:
                    records.append({"q": q, "code": code, "found": None, "error": str(e)})
            elif err_path.exists():
                try:
                    data = json.loads(err_path.read_text(encoding="utf-8"))
                    records.append({"q": q, "code": code, "found": None,
                                    "error": data.get("_error", "unknown")})
                except Exception:
                    records.append({"q": q, "code": code, "found": None, "error": "load error"})
            else:
                records.append({"q": q, "code": code, "found": None, "error": "결과 없음"})
    return records


def analyze(records: list[dict], detail: bool, fp_only: bool):
    TP = FP = TN = FN = ERR = 0
    fp_list = []
    fn_list = []
    err_list = []

    # 유형별, 문항별 집계
    type_stats = {code: {"TP": 0, "FP": 0, "TN": 0, "FN": 0, "ERR": 0} for code in ALL_TYPES}
    q_stats    = {q:    {"TP": 0, "FP": 0, "TN": 0, "FN": 0, "ERR": 0} for q    in ALL_QUESTIONS}

    for r in records:
        q, code = r["q"], r["code"]
        found   = r["found"]
        exp     = expected(q, code)

        if r["error"] or found is None:
            ERR += 1
            type_stats[code]["ERR"] += 1
            q_stats[q]["ERR"] += 1
            err_list.append(f"Q{q:02d}_{code}: {r['error']}")
            continue

        if found and exp:
            TP += 1; type_stats[code]["TP"] += 1; q_stats[q]["TP"] += 1
        elif found and not exp:
            FP += 1; type_stats[code]["FP"] += 1; q_stats[q]["FP"] += 1
            fp_list.append((q, code, r.get("confidence","?"), r.get("issues",[])))
        elif not found and exp:
            FN += 1; type_stats[code]["FN"] += 1; q_stats[q]["FN"] += 1
            fn_list.append((q, code))
        else:
            TN += 1; type_stats[code]["TN"] += 1; q_stats[q]["TN"] += 1

    total_valid = TP + FP + TN + FN
    precision = TP / (TP + FP) if (TP + FP) > 0 else float("nan")
    recall    = TP / (TP + FN) if (TP + FN) > 0 else float("nan")
    f1        = 2*precision*recall / (precision+recall) if (precision+recall) > 0 else float("nan")
    fpr       = FP / (FP + TN) if (FP + TN) > 0 else float("nan")   # 오탐율
    fnr       = FN / (FN + TP) if (FN + TP) > 0 else float("nan")   # 미탐율
    accuracy  = (TP + TN) / total_valid if total_valid > 0 else float("nan")

    # ── 전체 요약 출력 ────────────────────────────────────────
    w = 60
    print("=" * w)
    print("  전체 분석 결과")
    print("=" * w)
    print(f"  처리 완료: {total_valid:3d}  에러: {ERR:3d}  합계: {total_valid+ERR}")
    print(f"  TP={TP:3d}  FP={FP:3d}  TN={TN:3d}  FN={FN:3d}")
    print(f"  Precision  (정밀도): {precision:.3f}")
    print(f"  Recall     (재현율): {recall:.3f}")
    print(f"  F1-score           : {f1:.3f}")
    print(f"  Accuracy   (정확도): {accuracy:.3f}")
    print(f"  FPR (오탐율)       : {fpr:.3f}  ({FP}/{FP+TN})")
    print(f"  FNR (미탐율)       : {fnr:.3f}  ({FN}/{FN+TP})")
    print("=" * w)

    if fp_only:
        print("\n■ 오탐(FP) 목록")
        for q, code, conf, issues in fp_list:
            first = issues[0]["suspected"][:60] if issues else "-"
            print(f"  Q{q:02d} × {code} ({TYPE_NAME[code]})  conf={conf}")
            print(f"    → {first}")
        return

    # ── 유형별 분석 ───────────────────────────────────────────
    if detail:
        print("\n■ 유형별 분석")
        hdr = f"{'Code':<5} {'유형명':<18} {'TP':>3} {'FP':>3} {'TN':>3} {'FN':>3} {'ERR':>4}  {'정탐여부'}"
        print(hdr)
        print("-" * len(hdr))
        for code in ALL_TYPES:
            s = type_stats[code]
            detected = "✓" if s["TP"] > 0 else ("미탐" if s["FN"] > 0 else "-")
            print(f"  {code}  {TYPE_NAME[code]:<18} {s['TP']:>3} {s['FP']:>3} {s['TN']:>3} {s['FN']:>3} {s['ERR']:>4}  {detected}")

        # ── 문항별 분석 ───────────────────────────────────────
        print("\n■ 문항별 분석")
        hdr2 = f"{'Q':>3} {'주입유형':<6} {'탐지':>4} {'오탐수':>6} {'에러':>5}"
        print(hdr2)
        print("-" * len(hdr2))
        for q in ALL_QUESTIONS:
            s = q_stats[q]
            inj = INJECTED_TYPE[q]
            det = "✓" if s["TP"] > 0 else "✗"
            print(f"  Q{q:02d}  {inj}   {det}    FP={s['FP']:2d}   ERR={s['ERR']:2d}")

    # ── 오탐 목록 ────────────────────────────────────────────
    if fp_list:
        print(f"\n■ 오탐(FP) 상세 — 총 {len(fp_list)}건")
        for q, code, conf, issues in fp_list:
            first = issues[0]["suspected"][:70] if issues else "-"
            print(f"  Q{q:02d} × {code} ({TYPE_NAME[code]})  conf={conf}")
            print(f"    → {first}")

    if fn_list:
        print(f"\n■ 미탐(FN) — 총 {len(fn_list)}건")
        for q, code in fn_list:
            print(f"  Q{q:02d} × {code} ({TYPE_NAME[code]}) — 주입된 오류 미검출")

    if err_list:
        print(f"\n■ 에러 — 총 {len(err_list)}건")
        for e in err_list[:20]:
            print(f"  {e}")

    # ── JSON 저장 ────────────────────────────────────────────
    analysis = {
        "summary": {
            "TP": TP, "FP": FP, "TN": TN, "FN": FN, "ERR": ERR,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "accuracy": round(accuracy, 4),
            "fpr": round(fpr, 4), "fnr": round(fnr, 4),
        },
        "fp_list": [
            {"q": q, "type": code, "type_name": TYPE_NAME[code],
             "confidence": conf,
             "suspected": issues[0]["suspected"][:100] if issues else ""}
            for q, code, conf, issues in fp_list
        ],
        "fn_list": [{"q": q, "type": code} for q, code in fn_list],
        "type_stats": type_stats,
        "q_stats":    {str(k): v for k, v in q_stats.items()},
    }
    out = ROOT / "results" / "analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ 분석 저장: {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", action="store_true", help="유형별·문항별 상세 출력")
    parser.add_argument("--fp",     action="store_true", help="오탐 목록만 출력")
    args = parser.parse_args()

    records = load_results()
    covered = sum(1 for r in records if r["found"] is not None or r["error"] != "결과 없음")
    print(f"결과 파일 {covered}/400 로드 완료\n")
    analyze(records, detail=args.detail, fp_only=args.fp)


if __name__ == "__main__":
    main()
