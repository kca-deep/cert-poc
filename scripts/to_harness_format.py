"""
to_harness_format.py — 파이프라인 산출물(merged_filtered.json)을 cert-harness 출력
형태로 변환해, 두 시스템을 같은 잣대로 비교·검증할 수 있게 한다.

cert-harness(../cert-harness/experiments/harness_doc.py)는 문항마다 다음 형태로 출력한다:

    ### N번  (...)  parse=True  finish=stop  thinking=...자
    has_error=True  findings=K
      [1] (location) [error_type/confidence] quote검증=OK
          quote: '원문 인용'
          제안 : '수정 제안'

finding 스키마(harness_gemma_v2.py):
    {location, quote, error_type∈9종enum, reason, suggestion, confidence∈{높음,보통,낮음}}

파이프라인은 유형코드(A01~A21) + issues[{location, original, suspected, suggested}] 구조라
아래 매핑으로 하네스 형태에 투영한다. quote검증은 하네스와 동일하게
norm(quote) ⊂ norm(문항원문) 여부로 판정한다(norm = 모든 공백 제거).

산출물(기본 세션 디렉터리에 생성):
    harness_format.txt   — 하네스 텍스트 리포트(육안 diff 용)
    harness_format.json  — 하네스 스키마 JSON(프로그램 비교 용, _type_code 보존)

사용:
    python scripts/to_harness_format.py                      # 최신 세션 자동 선택
    python scripts/to_harness_format.py --session <id|경로>  # 특정 세션
    python scripts/to_harness_format.py --md <문항.md>        # 원문 명시(quote검증용)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_RESULTS = ROOT / "results" / "api"

# ── 유형코드 → 하네스 error_type(9종 enum) ──────────────────────────
#   enum: 맞춤법 띄어쓰기 문법비문 선택지누락 선택지중복 용어오류 사실오류 약어오기 기타
A_TO_ERROR_TYPE = {
    "A01": "선택지중복",   # 보기 중복
    "A02": "맞춤법",       # 오자(자모)
    "A03": "선택지누락",   # 보기개수 미달
    "A04": "맞춤법",       # 맞춤법
    "A05": "약어오기",     # 오자(영어 약어) DaS→DoS
    "A06": "띄어쓰기",     # 띄어쓰기
    "A07": "기타",         # 특수기호(?) 누락(발문)
    "A08": "문법비문",     # 매끄럽지 못한 문장
    "A09": "용어오류",     # 틀린 법령명
    "A10": "맞춤법",       # 오타+보기누락(대표: 오타)
    "A11": "기타",         # 낙서(편집표시1)
    "A12": "기타",         # 낙서(편집표시2)
    "A13": "기타",         # 문항번호 중복
    "A14": "기타",         # 정답 유출
    "A15": "선택지누락",   # 보기 없음(빈 보기)
    "A16": "맞춤법",       # 탈자
    "A17": "맞춤법",       # 지문 원문자 탈자
    "A18": "기타",         # 문장 전체 생략
    "A19": "기타",         # 특수기호 누락(지문)
    "A20": "용어오류",     # 틀린 법령 조항
    "A21": "용어오류",     # 단어 교체 오류
}

_CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]
_CONF_KO = {"high": "높음", "medium": "보통", "low": "낮음"}


def norm(s: str) -> str:
    """하네스와 동일: 모든 공백 제거 후 비교(quote검증용)."""
    return re.sub(r"\s+", "", s or "")


def map_location(loc: str) -> str:
    """파이프라인 location → 하네스 표기(지문/발문/선택지 ①…)."""
    if not loc:
        return "문항 전체"
    loc = loc.strip()
    if loc == "passage":
        return "지문"
    if loc == "stem":
        return "발문"
    if loc in ("choice_section", "choices", "choice"):
        return "선택지"
    m = re.match(r"choice[_-]?(\d+)", loc)
    if m:
        idx = int(m.group(1)) - 1
        return f"선택지 {_CIRCLED[idx]}" if 0 <= idx < len(_CIRCLED) else f"선택지 {m.group(1)}"
    return loc  # 알 수 없는 형태는 원본 유지


def map_error_type(type_code: str, issue: dict) -> str:
    """유형코드 → 하네스 error_type. A10(혼합)은 빈 보기면 선택지누락으로 보정."""
    base = A_TO_ERROR_TYPE.get(type_code, "기타")
    if type_code == "A10":
        orig = (issue.get("original") or "").strip()
        susp = issue.get("suspected") or ""
        if orig in _CIRCLED or "없" in susp or "빈" in susp:
            return "선택지누락"
    return base


def collect_timing(sess: Path) -> dict:
    """결과 JSON mtime 으로 실행시간을 복원한다(파이프라인은 별도 타이머 로그가 없음).

    파이프라인은 레이어 일괄처리(L0전체→L1전체→L2전체)라 '문항별' wall-time 은
    성립하지 않으므로 전체 wall-clock 과 레이어별 span 만 보고한다.

    반환: wall(전체초), layers{layer:(개수,소요초)}.
    """
    layer_dirs = {0: sess / "layer0", 1: sess / "layer1", 2: sess / "layer2"}
    all_mt: list[float] = []
    layers: dict[int, tuple[int, float]] = {}
    for L, d in layer_dirs.items():
        if not d.is_dir():
            continue
        mts = [f.stat().st_mtime for f in d.glob("*.json")]
        if mts:
            all_mt.extend(mts)
            layers[L] = (len(mts), max(mts) - min(mts))
    merged = sess / "merged_filtered.json"
    if merged.exists():
        all_mt.append(merged.stat().st_mtime)
    wall = (max(all_mt) - min(all_mt)) if all_mt else 0.0
    return {"wall": wall, "layers": layers}


def mmss(sec: float) -> str:
    s = max(0, int(round(sec)))
    h, m, x = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m:02d}:{x:02d}"


def parse_questions(md_path: Path) -> dict[int, str]:
    """하네스 parse_questions 와 동일 규칙(^## N.) 으로 문항 원문 분리(quote검증 소스)."""
    text = md_path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(##\s*\d+\.)\s*$", text)
    qs: dict[int, str] = {}
    for i in range(1, len(parts), 2):
        n = int(re.match(r"##\s*(\d+)\.", parts[i]).group(1))
        body = parts[i + 1] if i + 1 < len(parts) else ""
        qs[n] = parts[i].strip() + "\n" + body.strip()
    return qs


def build_findings(qd: dict, src: str) -> list[dict]:
    """한 문항의 모든 found 유형 → 하네스 finding 리스트(quote검증 포함)."""
    sn = norm(src)
    findings: list[dict] = []
    for code, r in qd.items():
        if not (isinstance(r, dict) and r.get("found")):
            continue
        conf = _CONF_KO.get(r.get("confidence", "high"), "보통")
        for it in (r.get("issues") or []):
            if not isinstance(it, dict):
                continue
            quote = it.get("original", "") or ""
            findings.append({
                "location": map_location(it.get("location", "")),
                "quote": quote,
                "error_type": map_error_type(code, it),
                "reason": it.get("suspected", "") or "",
                "suggestion": it.get("suggested", "") or "",
                "confidence": conf,
                "_type_code": code,                       # 역추적용(하네스엔 없는 보존 필드)
                "_quote_ok": bool(quote) and norm(quote) in sn,
            })
    return findings


def fmt_question(n: int, findings: list[dict]) -> str:
    """하네스 harness_doc.fmt 와 동일한 텍스트 블록.

    파이프라인은 레이어 일괄 처리(L0전체→L1전체→L2전체)라 문항별 wall-time 이
    성립하지 않는다(하네스의 문항별 LLM 지연과 달리). 그래서 시간은 '-' 로 두고,
    실제 실행시간은 푸터의 wall-clock·레이어별로 보고한다.
    """
    has_error = len(findings) > 0
    L = [
        f"\n{'=' * 70}",
        f"### {n}번  (-)  parse=True  finish=-  thinking=-",
        f"{'=' * 70}",
        f"has_error={has_error}  findings={len(findings)}",
    ]
    for i, f in enumerate(findings, 1):
        qok = "OK" if f["_quote_ok"] else "FAIL"
        L.append(f"  [{i}] ({f['location']}) [{f['error_type']}/{f['confidence']}] quote검증={qok}  ({f['_type_code']})")
        L.append(f"      quote: {f['quote']!r}")
        L.append(f"      제안 : {f['suggestion']!r}")
    return "\n".join(L)


def resolve_session(arg: str | None) -> Path:
    """세션 id/경로 해석. 미지정 시 merged_filtered.json 이 가장 최근인 세션."""
    if arg:
        p = Path(arg)
        if p.is_dir():
            return p
        cand = API_RESULTS / arg
        if cand.is_dir():
            return cand
        raise SystemExit(f"[error] 세션을 찾을 수 없음: {arg}")
    sessions = [
        d for d in API_RESULTS.iterdir()
        if d.is_dir() and (d / "merged_filtered.json").exists()
    ]
    if not sessions:
        raise SystemExit("[error] merged_filtered.json 을 가진 세션이 없습니다.")
    return max(sessions, key=lambda d: (d / "merged_filtered.json").stat().st_mtime)


def find_source_md(explicit: str | None, qcount: int) -> Path | None:
    """quote검증용 원문 .md. 명시 없으면 _uploads 에서 문항수 가장 가까운 것."""
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"[error] --md 파일 없음: {explicit}")
        return p
    uploads = API_RESULTS / "_uploads"
    if not uploads.is_dir():
        return None
    best, best_score = None, -1
    for md in uploads.glob("*.md"):
        try:
            n = len(parse_questions(md))
        except Exception:
            continue
        score = -abs(n - qcount)  # 문항 수가 가까울수록 우선
        if score > best_score:
            best, best_score = md, score
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description="파이프라인 결과를 cert-harness 형태로 변환")
    ap.add_argument("--session", help="세션 id 또는 디렉터리 경로(미지정 시 최신)")
    ap.add_argument("--md", help="문항 원문 .md(quote검증용, 미지정 시 자동탐색)")
    ap.add_argument("--out-dir", help="산출물 저장 디렉터리(기본: ../cert-harness/experiments)")
    args = ap.parse_args()

    sess = resolve_session(args.session)
    merged = json.loads((sess / "merged_filtered.json").read_text(encoding="utf-8"))
    qkeys = sorted(merged.keys(), key=lambda x: int(x))

    md = find_source_md(args.md, len(qkeys))
    src_map = parse_questions(md) if md else {}
    timing = collect_timing(sess)

    # 저장 위치: 기본은 cert-harness 쪽(거기서 하네스 실행 후 직접 비교).
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = ROOT.parent / "cert-harness" / "experiments"
    if not out_dir.is_dir():
        print(f"[warn] 출력 디렉터리 없음 → 세션 폴더로 대체: {out_dir}", file=sys.stderr)
        out_dir = sess
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 변환 ──
    out_json: dict[str, dict] = {}
    blocks: list[str] = []
    n_err = n_find = quote_total = quote_ok = 0
    for k in qkeys:
        n = int(k)
        src = src_map.get(n, "")
        findings = build_findings(merged[k], src)
        out_json[k] = {
            "analysis": "",  # 파이프라인엔 자유분석 필드 없음(하네스 형태 유지용 빈 값)
            "has_error": len(findings) > 0,
            "findings": findings,
        }
        blocks.append(fmt_question(n, findings))
        n_err += 1 if findings else 0
        for f in findings:
            n_find += 1
            quote_total += 1
            if f["_quote_ok"]:
                quote_ok += 1

    # ── 헤더/요약(하네스 harness_doc 동일 양식) ──
    src_name = md.name if md else "(원문없음: quote검증 생략)"
    wall = timing["wall"]
    header = (
        f"# 파이프라인→하네스 형태 변환  session={sess.name}  문항={len(qkeys)}  "
        f"source={src_name}  (변환기: scripts/to_harness_format.py)\n"
        f"# 실행: 3레이어 하이브리드(L0규칙+L1그룹LLM+L2per-type), provider=local, workers=3"
    )
    layer_bits = []
    for L in (0, 1, 2):
        if L in timing["layers"]:
            cnt, dur = timing["layers"][L]
            layer_bits.append(f"L{L} {cnt}건/{mmss(dur)}")
    footer = [
        f"\n{'#' * 70}",
        f"# 요약: 문항 {len(qkeys)},  has_error=true {n_err}/{len(qkeys)},  총 findings {n_find}",
    ]
    if quote_total:
        footer.append(f"#       quote 일치 {quote_ok}/{quote_total} ({100 * quote_ok // quote_total}%)")
    else:
        footer.append("#       quote 일치 -/- (원문 .md 없어 검증 생략)")
    footer.append(f"#       실행시간 wall-clock {mmss(wall)} ({wall:.1f}s),  provider=local, workers=3")
    if layer_bits:
        footer.append(f"#       레이어별 {' · '.join(layer_bits)} (문항별 시간은 레이어 일괄처리라 N/A)")

    text_report = header + "\n" + "\n".join(blocks) + "\n" + "\n".join(footer) + "\n"

    stem = f"pipeline_{sess.name}"
    txt_path = out_dir / f"{stem}_out.txt"
    json_path = out_dir / f"{stem}_out.json"
    txt_path.write_text(text_report, encoding="utf-8")
    json_path.write_text(json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print(text_report)
    print(f"\n[저장] {txt_path}")
    print(f"[저장] {json_path}")


if __name__ == "__main__":
    main()
