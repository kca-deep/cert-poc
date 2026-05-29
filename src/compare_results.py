"""
compare_results.py — per-type vs grouped 결과 비교 분석

사용법:
    python src/compare_results.py
    python src/compare_results.py --pertype results/v2_pertype --grouped results/v2_grouped
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

# 유형 → 그룹 매핑
TYPE_TO_GROUP = {
    "A02": "G1", "A04": "G1", "A05": "G1", "A06": "G1", "A16": "G1",
    "A01": "G2", "A03": "G2", "A10": "G2", "A13": "G2",
    "A15": "G2", "A17": "G2", "A18": "G2",
    "A07": "G3", "A08": "G3",
    "A09": "G4", "A19": "G4", "A20": "G4",
    "A11": "G5", "A12": "G5", "A14": "G5",
}

GROUP_NAMES = {
    "G1": "글자·표기 오류",
    "G2": "문항 구조 오류",
    "G3": "문장 품질",
    "G4": "법령·도메인 오류",
    "G5": "편집·출판 관리",
}


def load_pertype(result_dir: Path) -> dict[tuple[int, str], dict]:
    """per-type 결과 로드: {(q_num, type_code): result}"""
    data = {}
    for f in result_dir.glob("Q*_A*.json"):
        if "_ERROR" in f.name:
            continue
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            q = r.get("question_number")
            t = r.get("type_code")
            if q and t:
                data[(int(q), t)] = r
        except Exception:
            pass
    return data


def load_grouped(result_dir: Path) -> dict[tuple[int, str], dict]:
    """grouped 결과를 per-type 형식으로 펼쳐서 로드: {(q_num, type_code): result}"""
    data = {}
    for f in result_dir.glob("Q*_G*.json"):
        if "_ERROR" in f.name:
            continue
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            q = r.get("question_number")
            for sub in r.get("results", []):
                t = sub.get("type_code")
                if q and t:
                    data[(int(q), t)] = sub
        except Exception:
            pass
    return data


def compare(pertype_dir: Path, grouped_dir: Path):
    pt = load_pertype(pertype_dir)
    gr = load_grouped(grouped_dir)

    all_keys = sorted(set(pt.keys()) | set(gr.keys()))
    if not all_keys:
        print("결과 파일이 없습니다.")
        return

    # ── 1. 전체 지표 ─────────────────────────────────────────
    both_true  = 0  # 둘 다 found:true
    both_false = 0  # 둘 다 found:false
    pt_only    = 0  # per-type만 found:true (그룹화 미탐)
    gr_only    = 0  # grouped만 found:true  (그룹화 신규 탐지)
    pt_error   = 0
    gr_error   = 0

    discrepancies = []  # 불일치 목록

    for key in all_keys:
        q_num, t_code = key
        pt_r = pt.get(key, {})
        gr_r = gr.get(key, {})

        pt_found = pt_r.get("found") if "_error" not in pt_r else None
        gr_found = gr_r.get("found") if "_error" not in gr_r else None

        if pt_found is None:
            pt_error += 1
        if gr_found is None:
            gr_error += 1

        if pt_found is True and gr_found is True:
            both_true += 1
        elif pt_found is False and gr_found is False:
            both_false += 1
        elif pt_found is True and gr_found is False:
            pt_only += 1
            discrepancies.append(("그룹화 미탐", q_num, t_code, pt_r, gr_r))
        elif pt_found is False and gr_found is True:
            gr_only += 1
            discrepancies.append(("그룹화 신규탐지", q_num, t_code, pt_r, gr_r))

    total_valid = both_true + both_false + pt_only + gr_only
    match_rate  = (both_true + both_false) / total_valid * 100 if total_valid else 0

    print("=" * 65)
    print("  per-type vs grouped 비교 분석 결과")
    print("=" * 65)
    print(f"\n【전체 지표】")
    print(f"  비교 대상 (유형×문항)  : {total_valid:4d} 쌍")
    print(f"  일치 (둘 다 false)     : {both_false:4d}  ({both_false/total_valid*100:.1f}%)")
    print(f"  일치 (둘 다 true)      : {both_true:4d}  ({both_true/total_valid*100:.1f}%)")
    print(f"  전체 일치율            : {match_rate:.1f}%")
    print(f"  그룹화 미탐 (PT탐지↓)  : {pt_only:4d}  ← per-type만 found:true")
    print(f"  그룹화 신규탐지 (↑)    : {gr_only:4d}  ← grouped만 found:true")
    if pt_error or gr_error:
        print(f"  에러 (per-type)        : {pt_error:4d}")
        print(f"  에러 (grouped)         : {gr_error:4d}")

    # ── 2. 호출 효율성 ────────────────────────────────────────
    pt_files = len(list(pertype_dir.glob("Q*_A*.json")))
    gr_files = len(list(grouped_dir.glob("Q*_G*.json")))
    print(f"\n【호출 효율성】")
    print(f"  per-type 호출 수  : {pt_files:4d}")
    print(f"  grouped  호출 수  : {gr_files:4d}")
    if pt_files:
        print(f"  절감률            : {(1 - gr_files/pt_files)*100:.1f}%")

    # ── 3. 그룹별 비교 ────────────────────────────────────────
    print(f"\n【그룹별 일치율】")
    print(f"  {'그룹':<6} {'이름':<14} {'일치':>5} {'불일치(미탐)':>12} {'불일치(신규)':>12} {'일치율':>7}")
    print(f"  {'-'*58}")
    for gcode, gname in GROUP_NAMES.items():
        types_in_group = [t for t, g in TYPE_TO_GROUP.items() if g == gcode]
        g_match = g_pt_only = g_gr_only = 0
        for q_num, t_code in all_keys:
            if t_code not in types_in_group:
                continue
            pt_r = pt.get((q_num, t_code), {})
            gr_r = gr.get((q_num, t_code), {})
            pt_f = pt_r.get("found") if "_error" not in pt_r else None
            gr_f = gr_r.get("found") if "_error" not in gr_r else None
            if pt_f == gr_f and pt_f is not None:
                g_match += 1
            elif pt_f is True and gr_f is False:
                g_pt_only += 1
            elif pt_f is False and gr_f is True:
                g_gr_only += 1
        g_total = g_match + g_pt_only + g_gr_only
        rate = g_match / g_total * 100 if g_total else 0
        print(f"  {gcode:<6} {gname:<14} {g_match:>5} {g_pt_only:>12} {g_gr_only:>12} {rate:>6.1f}%")

    # ── 4. 불일치 상세 ────────────────────────────────────────
    if discrepancies:
        print(f"\n【불일치 상세】")
        for kind, q_num, t_code, pt_r, gr_r in sorted(discrepancies, key=lambda x: (x[1], x[2])):
            pt_issues = pt_r.get("issues", [])
            gr_issues = gr_r.get("issues", [])
            pt_orig = pt_issues[0].get("original", "") if pt_issues else ""
            gr_orig = gr_issues[0].get("original", "") if gr_issues else ""
            print(f"  [{kind}] Q{q_num:02d}-{t_code}")
            if pt_orig:
                print(f"    per-type: {pt_orig}")
            if gr_orig:
                print(f"    grouped : {gr_orig}")

    # ── 5. found:true 탐지 현황 ──────────────────────────────
    print(f"\n【found:true 탐지 현황 (문항별)】")
    q_nums = sorted(set(k[0] for k in all_keys))
    print(f"  {'Q':>4}  {'per-type 탐지 유형':<35} {'grouped 탐지 유형'}")
    print(f"  {'-'*70}")
    for q in q_nums:
        pt_found_types = sorted(t for (qn, t), r in pt.items()
                                if qn == q and r.get("found") is True)
        gr_found_types = sorted(t for (qn, t), r in gr.items()
                                if qn == q and r.get("found") is True)
        if pt_found_types or gr_found_types:
            print(f"  Q{q:02d}  {','.join(pt_found_types) or '-':<35} {','.join(gr_found_types) or '-'}")
    print()


def compare_grouped(v1_dir: Path, v2_dir: Path):
    """grouped v1 vs grouped v2 비교 — 프롬프트 개선 효과 측정."""
    v1 = load_grouped(v1_dir)
    v2 = load_grouped(v2_dir)

    all_keys = sorted(set(v1.keys()) | set(v2.keys()))
    if not all_keys:
        print("결과 파일이 없습니다.")
        return

    both_true = both_false = v1_only = v2_only = 0
    improvements = []   # v1 오탐 → v2 정상
    regressions  = []   # v1 정상 → v2 오탐

    for key in all_keys:
        q_num, t_code = key
        v1_r = v1.get(key, {})
        v2_r = v2.get(key, {})
        v1_f = v1_r.get("found") if "_error" not in v1_r else None
        v2_f = v2_r.get("found") if "_error" not in v2_r else None

        if v1_f is True  and v2_f is True:  both_true  += 1
        elif v1_f is False and v2_f is False: both_false += 1
        elif v1_f is True  and v2_f is False:
            v1_only += 1
            improvements.append((q_num, t_code, v1_r, v2_r))
        elif v1_f is False and v2_f is True:
            v2_only += 1
            regressions.append((q_num, t_code, v1_r, v2_r))

    total = both_true + both_false + v1_only + v2_only
    print("=" * 65)
    print("  grouped v1 vs grouped v2 개선 효과 분석")
    print("=" * 65)
    print(f"\n【전체 변화】")
    print(f"  비교 대상           : {total:4d} 쌍")
    print(f"  유지 (둘 다 false)  : {both_false:4d}  ({both_false/total*100:.1f}%)")
    print(f"  유지 (둘 다 true)   : {both_true:4d}  ({both_true/total*100:.1f}%)")
    print(f"  개선 (v1 true→v2 false) : {v1_only:4d}  ← 오탐 제거")
    print(f"  퇴행 (v1 false→v2 true) : {v2_only:4d}  ← 신규 탐지 or 퇴행")

    print(f"\n【그룹별 변화】")
    print(f"  {'그룹':<6} {'이름':<14} {'유지(F)':>7} {'유지(T)':>7} {'개선↑':>6} {'퇴행↓':>6}")
    print(f"  {'-'*50}")
    for gcode, gname in GROUP_NAMES.items():
        types_in = [t for t, g in TYPE_TO_GROUP.items() if g == gcode]
        g_bf = g_bt = g_v1 = g_v2 = 0
        for q_num, t_code in all_keys:
            if t_code not in types_in: continue
            v1_f = v1.get((q_num,t_code),{}).get("found")
            v2_f = v2.get((q_num,t_code),{}).get("found")
            if v1_f is True  and v2_f is True:   g_bt += 1
            elif v1_f is False and v2_f is False:  g_bf += 1
            elif v1_f is True  and v2_f is False:  g_v1 += 1
            elif v1_f is False and v2_f is True:   g_v2 += 1
        print(f"  {gcode:<6} {gname:<14} {g_bf:>7} {g_bt:>7} {g_v1:>6} {g_v2:>6}")

    if improvements:
        print(f"\n【개선 목록 (v1 오탐 → v2 제거)】")
        for q_num, t_code, v1_r, v2_r in sorted(improvements, key=lambda x: (x[0], x[1])):
            orig = (v1_r.get("issues") or [{}])[0].get("original", "")
            print(f"  Q{q_num:02d}-{t_code}  {orig}")

    if regressions:
        print(f"\n【퇴행 목록 (v1 정상 → v2 신규 탐지)】")
        for q_num, t_code, v1_r, v2_r in sorted(regressions, key=lambda x: (x[0], x[1])):
            orig = (v2_r.get("issues") or [{}])[0].get("original", "")
            print(f"  Q{q_num:02d}-{t_code}  {orig}")

    print(f"\n【found:true 탐지 현황 비교 (문항별)】")
    q_nums = sorted(set(k[0] for k in all_keys))
    print(f"  {'Q':>4}  {'v1 (이전)':.<40} {'v2 (개선후)'}")
    print(f"  {'-'*75}")
    for q in q_nums:
        v1_t = sorted(t for (qn,t),r in v1.items() if qn==q and r.get("found") is True)
        v2_t = sorted(t for (qn,t),r in v2.items() if qn==q and r.get("found") is True)
        if v1_t or v2_t:
            print(f"  Q{q:02d}  {','.join(v1_t) or '-':<40} {','.join(v2_t) or '-'}")
    print()


def three_way(pt_dir: Path, g1_dir: Path, g2_dir: Path):
    """per-type vs grouped-v1 vs grouped-v2 3방향 비교."""
    pt = load_pertype(pt_dir)
    g1 = load_grouped(g1_dir)
    g2 = load_grouped(g2_dir)

    all_keys = sorted(set(pt.keys()) | set(g1.keys()) | set(g2.keys()))
    q_nums   = sorted(set(k[0] for k in all_keys))
    all_types = sorted(set(k[1] for k in all_keys))

    def found(d, key):
        r = d.get(key, {})
        return r.get("found") if "_error" not in r else None

    # ── 1. 전체 found:true 건수 ───────────────────────────────
    pt_total = sum(1 for k in all_keys if found(pt, k) is True)
    g1_total = sum(1 for k in all_keys if found(g1, k) is True)
    g2_total = sum(1 for k in all_keys if found(g2, k) is True)

    print("=" * 70)
    print("  3방향 비교: per-type  vs  grouped-v1  vs  grouped-v2")
    print("=" * 70)

    # ── 2. 호출 효율 ─────────────────────────────────────────
    pt_calls = len(list(pt_dir.glob("Q*_A*.json")))
    g1_calls = len(list(g1_dir.glob("Q*_G*.json")))
    g2_calls = len(list(g2_dir.glob("Q*_G*.json")))
    print(f"\n【호출 효율】")
    print(f"  per-type   : {pt_calls:4d} 호출")
    print(f"  grouped-v1 : {g1_calls:4d} 호출  ({(1-g1_calls/pt_calls)*100:.0f}% 절감)")
    print(f"  grouped-v2 : {g2_calls:4d} 호출  ({(1-g2_calls/pt_calls)*100:.0f}% 절감)")

    # ── 3. found:true 건수 비교 ───────────────────────────────
    print(f"\n【전체 탐지 건수 (found:true)】")
    print(f"  per-type   : {pt_total:4d}건")
    print(f"  grouped-v1 : {g1_total:4d}건")
    print(f"  grouped-v2 : {g2_total:4d}건")

    # ── 4. 그룹별 found:true 건수 ────────────────────────────
    print(f"\n【그룹별 found:true 건수】")
    print(f"  {'그룹':<6} {'이름':<14} {'per-type':>9} {'grouped-v1':>11} {'grouped-v2':>11}")
    print(f"  {'-'*55}")
    for gcode, gname in GROUP_NAMES.items():
        types_in = [t for t, g in TYPE_TO_GROUP.items() if g == gcode]
        pt_c = sum(1 for k in all_keys if k[1] in types_in and found(pt, k) is True)
        g1_c = sum(1 for k in all_keys if k[1] in types_in and found(g1, k) is True)
        g2_c = sum(1 for k in all_keys if k[1] in types_in and found(g2, k) is True)
        print(f"  {gcode:<6} {gname:<14} {pt_c:>9} {g1_c:>11} {g2_c:>11}")

    # ── 5. 일치 패턴 분류 ─────────────────────────────────────
    all3_true = all3_false = 0
    pt_unique = g1_unique = g2_unique = 0
    pt_g2_agree_not_g1 = g1_g2_agree_not_pt = pt_g1_agree_not_g2 = 0

    for k in all_keys:
        pf, gf1, gf2 = found(pt,k), found(g1,k), found(g2,k)
        if pf is None or gf1 is None or gf2 is None:
            continue
        t = (pf, gf1, gf2)
        if   t == (True,  True,  True):  all3_true  += 1
        elif t == (False, False, False): all3_false += 1
        elif t == (True,  False, False): pt_unique  += 1
        elif t == (False, True,  False): g1_unique  += 1
        elif t == (False, False, True):  g2_unique  += 1
        elif t == (True,  False, True):  pt_g2_agree_not_g1 += 1
        elif t == (False, True,  True):  g1_g2_agree_not_pt += 1
        elif t == (True,  True,  False): pt_g1_agree_not_g2 += 1

    print(f"\n【일치 패턴 분류】")
    print(f"  3개 모두 true          : {all3_true:4d}건  ← 확실한 정탐 후보")
    print(f"  3개 모두 false         : {all3_false:4d}건  ← 확실한 정상")
    print(f"  per-type만 true        : {pt_unique:4d}건  ← 그룹화 시 미탐")
    print(f"  grouped-v1만 true      : {g1_unique:4d}건  ← v1 오탐 (v2에서 수정됨)")
    print(f"  grouped-v2만 true      : {g2_unique:4d}건  ← v2 신규 탐지")
    print(f"  per-type+v2 일치(v1 아님): {pt_g2_agree_not_g1:4d}건  ← v2 개선으로 per-type 수준 복구")
    print(f"  v1+v2 일치(per-type 아님): {g1_g2_agree_not_pt:4d}건  ← 그룹화 공통 탐지")
    print(f"  per-type+v1 일치(v2 아님): {pt_g1_agree_not_g2:4d}건  ← v2 퇴행")

    # ── 6. 문항별 3방향 탐지 현황 ────────────────────────────
    print(f"\n【문항별 found:true 탐지 유형 비교】")
    print(f"  {'Q':>4}  {'per-type':<28} {'grouped-v1':<28} {'grouped-v2'}")
    print(f"  {'-'*80}")
    for q in q_nums:
        pt_t  = sorted(t for (qn,t),r in pt.items()  if qn==q and r.get("found") is True)
        g1_t  = sorted(t for (qn,t),r in g1.items()  if qn==q and r.get("found") is True)
        g2_t  = sorted(t for (qn,t),r in g2.items()  if qn==q and r.get("found") is True)
        if pt_t or g1_t or g2_t:
            pt_s  = ','.join(pt_t)  or '-'
            g1_s  = ','.join(g1_t)  or '-'
            g2_s  = ','.join(g2_t)  or '-'
            print(f"  Q{q:02d}  {pt_s:<28} {g1_s:<28} {g2_s}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pertype",    type=str, default=str(ROOT / "results" / "v2_pertype"))
    parser.add_argument("--grouped",    type=str, default=str(ROOT / "results" / "v2_grouped"))
    parser.add_argument("--grouped-v2", type=str, default=None)
    parser.add_argument("--three-way",  action="store_true", help="3방향 비교 실행")
    args = parser.parse_args()

    gv2 = args.grouped_v2 or str(ROOT / "results" / "v2_grouped_v2")

    if args.three_way or args.grouped_v2:
        if args.three_way:
            three_way(Path(args.pertype), Path(args.grouped), Path(gv2))
        else:
            compare_grouped(Path(args.grouped), Path(gv2))
    else:
        compare(Path(args.pertype), Path(args.grouped))


if __name__ == "__main__":
    main()
