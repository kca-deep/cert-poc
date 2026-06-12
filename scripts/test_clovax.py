"""
test_clovax.py — Naver HyperCLOVA X(CLOVA Studio) 공급자 스모크 테스트.

문제집 전체가 아니라 **단일 문항 1개**(아래 SAMPLE_QUESTION, 합성 예시)를 clovax
공급자로 파이프라인의 실제 호출 경로(build_config → 프롬프트 로드 → call_with_retry)
그대로 태운다. "진행되는지"(설정/요청/응답 파싱)를 단계별로 출력한다.

사전 준비:
    .env 에 실제 CLOVASTUDIO_API_KEY(nv-...) 설정 후 실행.

사용:
    python scripts/test_clovax.py            # 기본 A02(오탈자) 유형으로 점검
    python scripts/test_clovax.py --type A21 # 다른 per-type 유형으로 점검
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서 한글/특수문자 출력 시 UnicodeEncodeError 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import core  # noqa: F401,E402  (src 를 sys.path 에 등록 + 평면 모듈 import 가능화)
from config import build_config, clovax_configured, print_lm_config  # noqa: E402
from core.pipeline import (  # noqa: E402
    call_with_retry,
    load_pertype_prompt,
    load_preamble,
    sanitize,
)

# ── 단일 테스트 문항 (합성 예시) ─────────────────────────────────────────
# 일부러 오탈자를 1곳 심었다: ④ "화장성" → 정상은 "확장성"(Scalability).
# A02(오탈자) 유형이면 found=true 가 기대값. (실제 차수 문항 아님 — 합성)
SAMPLE_QUESTION = """## 1. 다음 중 정보보안의 3대 요소(CIA)에 해당하지 않는 것은?

① 기밀성(Confidentiality)
② 무결성(Integrity)
③ 가용성(Availability)
④ 화장성(Scalability)
⑤ 부인방지(Non-repudiation)
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="A02", help="Layer2 per-type 유형 코드 (기본 A02 오탈자)")
    args = ap.parse_args()

    print("=" * 64)
    print(" HyperCLOVA X (clovax) 단일 문항 스모크 테스트")
    print("=" * 64)

    # 1) 키 확인 ----------------------------------------------------------
    if not clovax_configured():
        print("[중단] CLOVASTUDIO_API_KEY 가 설정되지 않았습니다(.env 확인).")
        return 2

    cfg = build_config("clovax")
    if (cfg.get("clova_api_key") or "").strip() in ("", "nv-..."):
        print("[중단] CLOVASTUDIO_API_KEY 가 플레이스홀더(nv-...) 입니다. 실제 키로 교체하세요.")
        return 2

    print_lm_config(cfg)

    # 2) 단일 문항 + 프롬프트 구성 (Layer2 per-type 경로와 동일) -----------
    print("\n[문항] (합성 단일 예시)")
    print("-" * 64)
    print(SAMPLE_QUESTION.rstrip())
    print("-" * 64)

    preamble = load_preamble()
    prompt = load_pertype_prompt(args.type)
    content = sanitize(prompt).replace("{{QUESTION_BLOCK}}", sanitize(SAMPLE_QUESTION))
    msgs = [
        {"role": "system", "content": preamble},
        {"role": "user", "content": content},
    ]

    # 3) 실제 호출 --------------------------------------------------------
    print(f"\n[호출] CLOVA Studio → model={cfg['clova_model']} base_url={cfg['clova_base_url']} · 유형={args.type}")
    result = call_with_retry(msgs, label=f"Q01_{args.type}", cfg=cfg)

    print("\n[결과]")
    if result is None:
        print("  반환 None (예외 경로) — 실패")
        return 1
    if "_error" in result:
        print(f"  실패: {result['_error']}")
        raw = result.get("_raw", "")
        if raw:
            print("  --- raw(앞 800자) ---")
            print("  " + raw[:800].replace("\n", "\n  "))
        return 1

    print("  성공 — 파싱된 JSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    found = result.get("found")
    n_issues = len(result.get("issues", []) or [])
    print(f"\n[요약] found={found} · issues={n_issues}건 — clovax 파이프라인 정상 동작")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
