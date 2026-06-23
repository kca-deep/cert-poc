"""
cli.py — 하이브리드 파이프라인 CLI 어댑터 (얇은 계층).

기존 `python src/hybrid_run.py --input ...` CLI를 그대로 재현한다.
로직은 전혀 갖지 않고, core.pipeline.run_pipeline()이 yield 하는 ProgressEvent를
사람이 읽기 좋은 콘솔 라인으로 포맷해 출력만 한다.

사용법:
    python src/cli.py --input data/파일.md
    python src/cli.py --input data/파일.md --q 13
    python src/cli.py --input data/파일.md --reset
"""

import argparse
import sys
from pathlib import Path

# stdout utf-8 재설정 (한글 출력 보장) — 원본 hybrid_run과 동일한 가드.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# core 를 먼저 import 하면 core/__init__ 이 src/ 를 sys.path 에 등록한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402,F401

from config import build_config, print_lm_config  # noqa: E402
from core.pipeline import run_pipeline  # noqa: E402

ROOT       = Path(__file__).resolve().parent.parent
DATA_PATH  = ROOT / "data" / "정보보호개요_X.md"
RESULT_DIR = ROOT / "results" / "holistic"


def _print_event(ev: dict) -> None:
    """ProgressEvent 하나를 사람이 읽기 좋은 콘솔 라인으로 출력한다."""
    kind = ev.get("event")

    if kind == "start":
        print(f"\n[holistic 검출] {ev['totalQ']}문항 — 문항당 LLM 1콜")

    elif kind == "q_done":
        q = ev["q"]
        findings = ev.get("findings", [])
        if findings:
            kinds = ", ".join(f.get("errorType", "?") for f in findings)
            print(f"  Q{q:02d}  found={len(findings)}건  [{kinds}]")
        else:
            print(f"  Q{q:02d}  오류 없음")

    elif kind == "done":
        print(f"\n{'='*60}")
        print(f"  탐지 건수: {ev['totalFound']}건")
        print(f"  총 소요 시간: {ev['elapsed']}s")
        print(f"{'='*60}")

    elif kind == "error":
        print(f"\n[오류] {ev['message']}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="3레이어 하이브리드 파이프라인 CLI")
    parser.add_argument("--input",  type=str, default=None)
    parser.add_argument("--q",      type=int, default=None)
    parser.add_argument("--reset",  action="store_true")
    parser.add_argument("--outdir", type=str, default=None)
    parser.add_argument("--provider", choices=("local", "claude"), default=None,
                        help="LLM 공급자 (미지정 시 .env 의 LLM_PROVIDER)")
    args = parser.parse_args()

    data_path  = Path(args.input) if args.input else DATA_PATH
    result_dir = Path(args.outdir) if args.outdir else RESULT_DIR
    result_dir.mkdir(parents=True, exist_ok=True)

    overrides = {"provider"} if args.provider else None
    print_lm_config(build_config(args.provider), overrides)
    print(f"입력: {data_path.name}")
    print(f"출력: {result_dir}")

    md_text = data_path.read_text(encoding="utf-8")

    for ev in run_pipeline(md_text, result_dir, args.q, args.reset,
                           provider=args.provider):
        _print_event(ev)


if __name__ == "__main__":
    main()
