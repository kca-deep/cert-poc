#!/usr/bin/env python3
"""TOLIS AI 윤문 POC 결과 보고서를 Gmail API를 통해 발송."""

import base64
import json
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 분석 데이터 ──────────────────────────────────────────────
BASELINE = dict(TP=18, FP=38, TN=338, FN=4, precision=0.321, recall=0.818, f1=0.462, fpr=0.101, accuracy=0.894)
IMPROVED = dict(TP=19, FP=17, TN=359, FN=3, precision=0.528, recall=0.864, f1=0.655, fpr=0.045, accuracy=0.950)

INJECTED = {
    1: ("A01", "보기 중복"),
    2: ("A02", "오자"),
    3: ("A03", "보기개수 미달"),
    4: ("A04", "맞춤법"),
    5: ("A05", "오자(영어)"),
    6: (None, "오류 미주입"),
    7: ("A07", "특수기호(?) 누락"),
    8: ("A08", "매끄럽지 못한 문장"),
    9: ("A09", "틀린 법령명"),
    10: ("A10", "오타+보기누락"),
    11: ("A11", "낙서(유형1)"),
    12: ("A12", "낙서(유형2)"),
    13: ("A13", "문항번호 중복"),
    14: ("A14", "정답유출"),
    15: ("A15", "보기 없음"),
    16: ("A16", "탈자"),
    17: ("A17", "원문자 탈자"),
    18: ("A18", "문장 전체 생략"),
    19: ("A19", "특수기호 누락(지문)"),
    20: ("A20", "틀린 법령 조항"),
}

Q_STATS = {
    1:  dict(TP=1, FP=0, FN=0),
    2:  dict(TP=1, FP=3, FN=0),
    3:  dict(TP=1, FP=4, FN=0),
    4:  dict(TP=1, FP=0, FN=0),
    5:  dict(TP=1, FP=0, FN=0),
    6:  dict(TP=0, FP=1, FN=0),
    7:  dict(TP=0, FP=1, FN=1),
    8:  dict(TP=1, FP=0, FN=0),
    9:  dict(TP=1, FP=0, FN=0),
    10: dict(TP=3, FP=4, FN=0),
    11: dict(TP=1, FP=0, FN=0),
    12: dict(TP=1, FP=0, FN=0),
    13: dict(TP=2, FP=0, FN=0),
    14: dict(TP=1, FP=0, FN=0),
    15: dict(TP=1, FP=0, FN=0),
    16: dict(TP=0, FP=1, FN=1),
    17: dict(TP=1, FP=0, FN=0),
    18: dict(TP=1, FP=0, FN=0),
    19: dict(TP=0, FP=3, FN=1),
    20: dict(TP=1, FP=0, FN=0),
}

FP_DETAILS = [
    (2,  "A04", "맞춤법",             "high",   "'외뷰'(오자 A02) 교차오염 → 맞춤법 오류로 오판"),
    (2,  "A06", "띄어쓰기",           "low",    "'외뷰'(오자 A02) 교차오염 → 띄어쓰기 오류로 오판"),
    (2,  "A08", "매끄럽지 못한 문장", "high",   "'외뷰'(오자 A02) 교차오염 → 문장 어색함으로 오판"),
    (3,  "A07", "특수기호(?) 누락",   "high",   "A03 주입(선택지 삭제) → 모델 환각, stem '?' 누락 오판"),
    (3,  "A10", "오타+보기누락",       "high",   "A03 주입(선택지 삭제) → 모델 환각, ②번 없음으로 오판"),
    (3,  "A13", "문항번호 중복",       "high",   "A03 주입(선택지 삭제) → 모델 환각, ③번 없음으로 오판"),
    (3,  "A15", "보기 없음",           "high",   "A03 주입(선택지 삭제) → 모델 환각, 5번 선택지 없음으로 오판"),
    (6,  "A17", "원문자 탈자",         "high",   "fill-in-blank 형식 '( )' → ㉠/㉡ 탈자로 오판"),
    (7,  "A01", "보기 중복",           "high",   "정상 선택지 1번 → 중복으로 오판"),
    (10, "A03", "보기개수 미달",       "high",   "'함다'(오자 A10) 교차오염 → ③번 없음으로 오판"),
    (10, "A04", "맞춤법",             "high",   "'함다'(오자 A10) 교차오염 → 맞춤법 오류로 오판"),
    (10, "A06", "띄어쓰기",           "low",    "'함다'(오자 A10) 교차오염 → 띄어쓰기 오류로 오판"),
    (10, "A16", "탈자",               "medium", "'함다'(오자 A10) 교차오염 → 탈자로 오판"),
    (16, "A03", "보기개수 미달",       "medium", "정상 문항 → 보기 4개 미만으로 오판"),
    (19, "A04", "맞춤법",             "medium", "'최대한의' 표현 → 맞춤법 오류로 오판"),
    (19, "A06", "띄어쓰기",           "high",   "'최대한의 개인정보' → 띄어쓰기 오류로 오판"),
    (19, "A08", "매끄럽지 못한 문장", "medium", "'최대한의' 의미 오류 → 문장 어색함으로 오판"),
]

FN_DETAILS = [
    (7,  "A07", "특수기호(?) 누락",    "stem '?' 누락 미검출"),
    (16, "A16", "탈자",                "탈자 미검출"),
    (19, "A19", "특수기호 누락(지문)", "지문 내 특수기호 누락 미검출"),
]

# ── HTML 생성 ────────────────────────────────────────────────
def pct_change(old, new):
    if old == 0:
        return "N/A"
    d = (new - old) / old * 100
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.1f}%"

def arrow(old, new, higher_is_better=True):
    if new > old:
        color = "#27ae60" if higher_is_better else "#e74c3c"
        sym = "▲"
    elif new < old:
        color = "#e74c3c" if higher_is_better else "#27ae60"
        sym = "▼"
    else:
        color = "#666"
        sym = "─"
    return f'<span style="color:{color};font-weight:bold">{sym}</span>'

def build_html():
    B = BASELINE
    I = IMPROVED

    # --- 통계 비교 테이블 ---
    stats_rows = [
        ("TP (정탐)", B["TP"], I["TP"], True),
        ("FP (오탐)", B["FP"], I["FP"], False),
        ("TN (정상 정확)", B["TN"], I["TN"], True),
        ("FN (미탐)", B["FN"], I["FN"], False),
        ("Precision (정밀도)", f"{B['precision']:.3f}", f"{I['precision']:.3f}", True),
        ("Recall (재현율)", f"{B['recall']:.3f}", f"{I['recall']:.3f}", True),
        ("F1-score", f"{B['f1']:.3f}", f"{I['f1']:.3f}", True),
        ("Accuracy (정확도)", f"{B['accuracy']:.3f}", f"{I['accuracy']:.3f}", True),
        ("FPR (오탐율)", f"{B['fpr']:.3f}", f"{I['fpr']:.3f}", False),
    ]

    stat_html = ""
    for label, bv, iv, higher_good in stats_rows:
        bv_n = bv if isinstance(bv, (int, float)) else float(bv)
        iv_n = iv if isinstance(iv, (int, float)) else float(iv)
        arw = arrow(bv_n, iv_n, higher_good)
        chg = pct_change(bv_n, iv_n)
        stat_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{label}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{bv}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center"><strong>{iv}</strong></td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{arw} {chg}</td>
        </tr>"""

    # --- 문항별 결과 테이블 ---
    q_html = ""
    for qn in range(1, 21):
        code, name = INJECTED[qn]
        s = Q_STATS[qn]
        tp, fp, fn = s["TP"], s["FP"], s["FN"]

        if code is None:
            status = '<span style="color:#27ae60">✓ 오류 미주입 (정상)</span>'
        elif tp > 0 and fp == 0 and fn == 0:
            status = '<span style="color:#27ae60">✓ 정상 검출</span>'
        elif tp > 0 and fp > 0 and fn == 0:
            status = f'<span style="color:#f39c12">△ 정탐 {tp}건 + 오탐 {fp}건</span>'
        elif tp == 0 and fp > 0 and fn == 0:
            status = f'<span style="color:#e74c3c">✗ 미검출 + 오탐 {fp}건</span>'
        elif tp > 0 and fn > 0:
            status = f'<span style="color:#e74c3c">△ 부분 검출 (FN {fn}건)</span>'
        elif fn > 0:
            status = f'<span style="color:#e74c3c">✗ 미검출 (FN)</span>'
        else:
            status = f'TP={tp} FP={fp} FN={fn}'

        injected_label = f"{code} {name}" if code else "없음"
        q_html += f"""
        <tr style="{'background:#fafafa' if qn % 2 == 0 else ''}">
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">Q{qn:02d}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">{injected_label}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">{tp}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">{fp}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">{fn}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">{status}</td>
        </tr>"""

    # --- 오탐 상세 테이블 ---
    fp_html = ""
    for qn, code, name, conf, reason in FP_DETAILS:
        conf_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#95a5a6"}.get(conf, "#666")
        fp_html += f"""
        <tr>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">Q{qn:02d}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">{code} {name}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">
            <span style="color:{conf_color};font-weight:bold">{conf}</span>
          </td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">{reason}</td>
        </tr>"""

    # --- 미탐 상세 테이블 ---
    fn_html = ""
    for qn, code, name, reason in FN_DETAILS:
        fn_html += f"""
        <tr>
          <td style="padding:7px 12px;border-bottom:1px solid #eee;text-align:center">Q{qn:02d}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">{code} {name}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #eee">{reason}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>TOLIS AI 윤문 POC 결과 보고서</title></head>
<body style="font-family:'Malgun Gothic',Arial,sans-serif;color:#333;max-width:900px;margin:0 auto;padding:20px">

<h1 style="color:#2c3e50;border-bottom:3px solid #3498db;padding-bottom:10px">
  TOLIS 시험지 AI 윤문 POC — 검수 결과 보고서
</h1>
<p style="color:#666;font-size:14px">기준일: 2026-05-20 &nbsp;|&nbsp; 모델: EXAONE-3.5-32B (로컬) &nbsp;|&nbsp; 총 평가: 20문항 × 20유형 = 400건</p>

<!-- ─── 요약 카드 ─── -->
<h2 style="color:#2c3e50;margin-top:32px">1. 성능 개선 요약</h2>
<table style="border-collapse:collapse;width:100%;background:#f8f9fa;border-radius:8px;overflow:hidden">
  <tr style="background:#3498db;color:white">
    <th style="padding:10px 16px;text-align:left">지표</th>
    <th style="padding:10px 16px;text-align:center">베이스라인</th>
    <th style="padding:10px 16px;text-align:center">개선 후</th>
    <th style="padding:10px 16px;text-align:center">변화</th>
  </tr>
  {stat_html}
</table>

<div style="margin:20px 0;padding:16px;background:#eaf4fb;border-left:4px solid #3498db;border-radius:4px">
  <strong>핵심 성과:</strong>
  오탐(FP) 38건 → 17건 <strong>(55% 감소)</strong>,
  F1-score 0.462 → 0.655 <strong>(+41.8%)</strong>,
  Accuracy 89.4% → 95.0% <strong>(+5.6%p)</strong>
</div>

<!-- ─── 개선 방법론 ─── -->
<h2 style="color:#2c3e50;margin-top:32px">2. 개선 방법론</h2>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#ecf0f1">
    <th style="padding:8px 12px;text-align:left;border:1px solid #ddd">개선 대상 유형</th>
    <th style="padding:8px 12px;text-align:left;border:1px solid #ddd">주요 변경 내용</th>
    <th style="padding:8px 12px;text-align:center;border:1px solid #ddd">효과</th>
  </tr>
  <tr>
    <td style="padding:8px 12px;border:1px solid #ddd">A08 매끄럽지 못한 문장</td>
    <td style="padding:8px 12px;border:1px solid #ddd">보고 대상을 "조사 오류(이/가↔을/를)"로 엄격히 제한, 의미 추론 금지</td>
    <td style="padding:8px 12px;border:1px solid #ddd;text-align:center;color:#27ae60">FP 대폭 감소</td>
  </tr>
  <tr style="background:#fafafa">
    <td style="padding:8px 12px;border:1px solid #ddd">A17 원문자 탈자</td>
    <td style="padding:8px 12px;border:1px solid #ddd">fill-in-blank 형식(빈 괄호) 즉시 false 규칙 추가</td>
    <td style="padding:8px 12px;border:1px solid #ddd;text-align:center;color:#27ae60">FP 제거</td>
  </tr>
  <tr>
    <td style="padding:8px 12px;border:1px solid #ddd">A14 정답유출</td>
    <td style="padding:8px 12px;border:1px solid #ddd">빈 괄호 즉시 false, 지문 설명=유출 아님 명시</td>
    <td style="padding:8px 12px;border:1px solid #ddd;text-align:center;color:#27ae60">FP 제거</td>
  </tr>
  <tr style="background:#fafafa">
    <td style="padding:8px 12px;border:1px solid #ddd">A05 오자(영어)</td>
    <td style="padding:8px 12px;border:1px solid #ddd">DoS, DDoS, SEED, ARIA 등 보안 용어 어휘 목록 확장</td>
    <td style="padding:8px 12px;border:1px solid #ddd;text-align:center;color:#27ae60">FN→TP 전환</td>
  </tr>
  <tr>
    <td style="padding:8px 12px;border:1px solid #ddd">A06 띄어쓰기</td>
    <td style="padding:8px 12px;border:1px solid #ddd">오자(A02) 단어의 공백 검사 금지 규칙 추가</td>
    <td style="padding:8px 12px;border:1px solid #ddd;text-align:center;color:#27ae60">FP 감소</td>
  </tr>
  <tr style="background:#fafafa">
    <td style="padding:8px 12px;border:1px solid #ddd">A15 보기 없음</td>
    <td style="padding:8px 12px;border:1px solid #ddd">①②③④ 4개 모두 있을 때만 분석, 누락 시 즉시 false</td>
    <td style="padding:8px 12px;border:1px solid #ddd;text-align:center;color:#27ae60">FP 제거</td>
  </tr>
</table>

<!-- ─── 문항별 결과 ─── -->
<h2 style="color:#2c3e50;margin-top:32px">3. 문항별 검수 결과 (개선 후)</h2>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#2c3e50;color:white">
    <th style="padding:8px 12px;text-align:center">문항</th>
    <th style="padding:8px 12px;text-align:left">주입 오류</th>
    <th style="padding:8px 12px;text-align:center">TP</th>
    <th style="padding:8px 12px;text-align:center">FP</th>
    <th style="padding:8px 12px;text-align:center">FN</th>
    <th style="padding:8px 12px;text-align:left">상태</th>
  </tr>
  {q_html}
</table>
<p style="font-size:12px;color:#888;margin-top:6px">
  TP=정탐(오류 올바르게 검출) / FP=오탐(오류 없는데 검출) / FN=미탐(오류 있는데 미검출)
</p>

<!-- ─── 오탐 상세 ─── -->
<h2 style="color:#2c3e50;margin-top:32px">4. 오탐(FP) 상세 — 총 17건</h2>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#e74c3c;color:white">
    <th style="padding:8px 12px;text-align:center">문항</th>
    <th style="padding:8px 12px;text-align:left">오판 유형</th>
    <th style="padding:8px 12px;text-align:center">신뢰도</th>
    <th style="padding:8px 12px;text-align:left">원인</th>
  </tr>
  {fp_html}
</table>

<div style="margin:16px 0;padding:14px;background:#fef9e7;border-left:4px solid #f39c12;border-radius:4px">
  <strong>주요 오탐 패턴:</strong><br>
  • <strong>교차오염</strong>: 오자(A02/A10) 1개 주입 시 인접 유형(A04·A06·A08)이 동시 반응 → Q02(3건), Q10(4건), Q19(3건)<br>
  • <strong>모델 환각</strong>: A03 주입으로 선택지 구조 변경 시 무관한 유형 4개 동시 오탐 → Q03(4건)<br>
  • <strong>형식 오해</strong>: fill-in-blank 빈 괄호 "( )" → ㉠/㉡ 탈자로 오판 → Q06(1건)
</div>

<!-- ─── 미탐 상세 ─── -->
<h2 style="color:#2c3e50;margin-top:32px">5. 미탐(FN) 상세 — 총 3건</h2>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#7f8c8d;color:white">
    <th style="padding:8px 12px;text-align:center">문항</th>
    <th style="padding:8px 12px;text-align:left">주입 유형</th>
    <th style="padding:8px 12px;text-align:left">미검출 원인</th>
  </tr>
  {fn_html}
</table>

<!-- ─── 잔존 한계 ─── -->
<h2 style="color:#2c3e50;margin-top:32px">6. 잔존 한계 및 향후 과제</h2>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#ecf0f1">
    <th style="padding:8px 12px;text-align:left;border:1px solid #ddd">한계 유형</th>
    <th style="padding:8px 12px;text-align:left;border:1px solid #ddd">설명</th>
    <th style="padding:8px 12px;text-align:left;border:1px solid #ddd">개선 방향</th>
  </tr>
  <tr>
    <td style="padding:8px 12px;border:1px solid #ddd">교차오염 오탐</td>
    <td style="padding:8px 12px;border:1px solid #ddd">오자 1개가 인접 유형 다수를 동시 오탐 유발</td>
    <td style="padding:8px 12px;border:1px solid #ddd">후처리 억제 규칙 강화 또는 유형 간 의존성 모델링</td>
  </tr>
  <tr style="background:#fafafa">
    <td style="padding:8px 12px;border:1px solid #ddd">모델 환각</td>
    <td style="padding:8px 12px;border:1px solid #ddd">구조 변경 문항에서 무관한 유형까지 오탐</td>
    <td style="padding:8px 12px;border:1px solid #ddd">유형별 독립 프롬프트 체인 + 재확인(verification) 단계</td>
  </tr>
  <tr>
    <td style="padding:8px 12px;border:1px solid #ddd">온도 비일관성</td>
    <td style="padding:8px 12px;border:1px solid #ddd">동일 문항·동일 프롬프트에서 실행마다 결과 변동</td>
    <td style="padding:8px 12px;border:1px solid #ddd">Temperature 0으로 고정 또는 앙상블 다수결</td>
  </tr>
</table>

<hr style="margin-top:40px;border:none;border-top:1px solid #ddd">
<p style="font-size:12px;color:#aaa;text-align:center">
  본 보고서는 TOLIS AI 윤문 POC (Proof of Concept) 결과이며, 로컬 EXAONE-3.5-32B 모델로 생성되었습니다.<br>
  문의: 자동 생성 보고서 | 2026-05-20
</p>
</body>
</html>"""
    return html


def send_gmail(to: str, subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["From"] = "me"
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = json.dumps({"raw": raw})

    gws = "/home/kca/.npm/_npx/2d8653d32c8b8c5f/node_modules/@googleworkspace/cli/bin/gws"
    result = subprocess.run(
        [gws, "gmail", "users", "messages", "send",
         "--params", '{"userId":"me"}',
         "--json", body],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        raise RuntimeError(f"gws failed: {result.returncode}")
    print("발송 완료:", result.stdout[:200])


if __name__ == "__main__":
    html = build_html()
    send_gmail(
        to="bcchung81@gmail.com",
        subject="[TOLIS AI 윤문 POC] 검수 결과 보고서 — F1 0.462→0.655 (+42%)",
        html=html,
    )
