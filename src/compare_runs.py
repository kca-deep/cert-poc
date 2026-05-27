"""
compare_runs.py — full_run vs param_run 비교 분석

사용법:
    python src/compare_runs.py                # full_run(v5) vs param_run 비교
    python src/compare_runs.py --questions 4 5 11 13  # 특정 문항만
"""

import argparse, json, sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8","utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent

ALL_TYPES     = [f"A{n:02d}" for n in range(1, 21)]
ALL_QUESTIONS = list(range(1, 21))

INJECTED_TYPE = {
    1:"A01",2:"A02",3:"A03",4:"A04",5:"A05",6:"A06",7:"A07",8:"A08",
    9:"A09",10:"A10",11:"A11",12:"A12",13:"A13",14:"A14",15:"A15",
    16:"A16",17:"A17",18:"A18",19:"A19",20:"A20",
}
TYPE_NAME = {
    "A01":"보기 중복","A02":"오자","A03":"보기개수 미달","A04":"맞춤법",
    "A05":"오자(영어)","A06":"띄어쓰기","A07":"특수기호 누락","A08":"매끄럽지 못한 문장",
    "A09":"틀린 법령명","A10":"오타+보기누락","A11":"낙서(유형1)","A12":"낙서(유형2)",
    "A13":"문항번호 중복","A14":"정답유출","A15":"보기 없음","A16":"탈자",
    "A17":"원문자 탈자","A18":"문장 전체 생략","A19":"특수기호 누락(지문)","A20":"틀린 법령 조항",
}
ALLOWED_CROSS = {(10,"A02"),(10,"A15"),(13,"A03")}

def expected(q, code):
    if INJECTED_TYPE.get(q)==code: return True
    if (q,code) in ALLOWED_CROSS: return True
    return False

def load_run(result_dir, q_filter):
    records = {}
    for q in ALL_QUESTIONS:
        if q_filter and q not in q_filter: continue
        for code in ALL_TYPES:
            label    = f"Q{q:02d}_{code}"
            ok_path  = result_dir / f"{label}.json"
            err_path = result_dir / f"{label}_ERROR.json"
            if ok_path.exists():
                try:
                    data = json.loads(ok_path.read_text(encoding="utf-8"))
                    records[(q,code)] = {"found":data.get("found"),"conf":data.get("confidence","?")}
                except: records[(q,code)] = {"found":None,"conf":"?"}
            elif err_path.exists():
                records[(q,code)] = {"found":None,"conf":"ERR"}
            else:
                records[(q,code)] = {"found":None,"conf":"없음"}
    return records

def compute_metrics(records, q_filter):
    TP=FP=TN=FN=ERR=0
    for (q,code), r in records.items():
        if q_filter and q not in q_filter: continue
        found = r["found"]; exp = expected(q,code)
        if found is None: ERR+=1; continue
        if found and exp:    TP+=1
        elif found and not exp: FP+=1
        elif not found and exp: FN+=1
        else:                TN+=1
    total = TP+FP+TN+FN
    prec   = TP/(TP+FP) if TP+FP>0 else float("nan")
    recall = TP/(TP+FN) if TP+FN>0 else float("nan")
    f1     = 2*prec*recall/(prec+recall) if prec+recall>0 else float("nan")
    fpr    = FP/(FP+TN) if FP+TN>0 else float("nan")
    acc    = (TP+TN)/total if total>0 else float("nan")
    return {"TP":TP,"FP":FP,"TN":TN,"FN":FN,"ERR":ERR,
            "Precision":prec,"Recall":recall,"F1":f1,"FPR":fpr,"Accuracy":acc}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--questions", nargs="+", type=int)
    args = p.parse_args()
    qf = args.questions

    full_dir  = ROOT/"results"/"full_run"
    param_dir = ROOT/"results"/"param_run"

    if not param_dir.exists():
        print("param_run 결과 없음. 먼저 param_run.py 실행 필요"); return

    full  = load_run(full_dir,  qf)
    param = load_run(param_dir, qf)

    if not full:  print("full_run 결과 없음"); return
    if not param: print("param_run 결과 없음"); return

    # 공통 문항만 비교
    common_keys = set(full.keys()) & set(param.keys())
    full_c  = {k:v for k,v in full.items()  if k in common_keys}
    param_c = {k:v for k,v in param.items() if k in common_keys}

    fm = compute_metrics(full_c,  qf)
    pm = compute_metrics(param_c, qf)

    scope = f"Q{sorted(qf)}" if qf else "전체"
    print(f"\n{'='*62}")
    print(f"  비교 분석 — {scope}  ({len(common_keys)//20}문항 × 20유형 = {len(common_keys)}셀)")
    print(f"{'='*62}")
    print(f"{'지표':<20} {'full_run(v5)':>12} {'param_run':>12} {'변화':>8}")
    print(f"{'-'*62}")
    for key in ["Accuracy","FPR","FNR_calc","Precision","Recall","F1","TP","FP","TN","FN","ERR"]:
        if key == "FNR_calc":
            fv = fm["FN"]/(fm["FN"]+fm["TP"]) if fm["FN"]+fm["TP"]>0 else float("nan")
            pv = pm["FN"]/(pm["FN"]+pm["TP"]) if pm["FN"]+pm["TP"]>0 else float("nan")
            label = "미탐율 (FNR)"
        else:
            fv, pv, label = fm.get(key,0), pm.get(key,0), key
        if isinstance(fv, float):
            delta = pv-fv
            arrow = ("▲" if delta>0 else "▼") if abs(delta)>0.001 else " "
            bad_if_up = key in ("FPR","FNR_calc")
            trend = f"{arrow}{abs(delta):.3f}"
            print(f"  {label:<18} {fv:>12.3f} {pv:>12.3f} {trend:>8}")
        else:
            delta = pv-fv
            arrow = ("▲" if delta>0 else "▼") if delta!=0 else " "
            print(f"  {label:<18} {fv:>12d} {pv:>12d} {arrow+str(abs(delta)):>8}")
    print(f"{'='*62}")

    # 문항별 FP 비교
    print("\n■ 문항별 FP 비교 (full_run vs param_run)")
    print(f"{'Q':>3} {'주입유형':<6} {'full FP':>8} {'param FP':>9} {'탐지F':>6} {'탐지P':>6}")
    print("-"*45)
    q_stats = {}
    for (q,code), fr in full_c.items():
        pr = param_c.get((q,code),{"found":None,"conf":"?"})
        exp = expected(q,code)
        if q not in q_stats: q_stats[q] = {"fFP":0,"pFP":0,"fTP":False,"pTP":False}
        if fr["found"] and not exp: q_stats[q]["fFP"]+=1
        if pr["found"] and not exp: q_stats[q]["pFP"]+=1
        if fr["found"] and exp: q_stats[q]["fTP"]=True
        if pr["found"] and exp: q_stats[q]["pTP"]=True
    for q in sorted(q_stats.keys()):
        s = q_stats[q]
        inj = INJECTED_TYPE[q]
        delta = s["pFP"]-s["fFP"]
        arrow = ("▼" if delta<0 else ("▲" if delta>0 else " "))
        print(f"  Q{q:02d}  {inj}  {s['fFP']:>7d}  {s['pFP']:>9d}  {'✓' if s['fTP'] else '✗':>6}  {'✓' if s['pTP'] else '✗':>5}  {arrow}{abs(delta) if delta!=0 else ''}")

if __name__ == "__main__":
    main()
