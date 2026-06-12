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
RESULT_DIR = ROOT / "results" / "hybrid"

_LAYER_NAMES = {
    0: "코드 기반 탐지 (A01·A03·A13·A15·A17·A18)",
    1: "그룹 LLM (G1·G4·G5)",
    2: "per-type LLM (A02·A07·A08·A10·A12·A16·A19·A21)",
}


def _print_event(ev: dict) -> None:
    """ProgressEvent 하나를 사람이 읽기 좋은 콘솔 라인으로 출력한다."""
    kind = ev.get("event")

    if kind == "layer_start":
        layer = ev["layer"]
        name  = _LAYER_NAMES.get(layer, "")
        total = ev.get("totalQ")
        suffix = f"  ({total}문항)" if total is not None else ""
        print(f"\n[Layer {layer}] {name}{suffix}")

    elif kind == "q_layer0_done":
        q = ev["q"]
        found = sorted(t for t, f in ev["types"].items() if f)
        if found:
            print(f"  Q{q:02d}  found={','.join(found)}")

    elif kind == "q_type_done":
        q    = ev["q"]
        t    = ev["typeCode"]
        conf = ev.get("confidence", "")
        if ev["found"]:
            tag = f"found  conf={conf}" if conf else "found"
            print(f"  Q{q:02d}-{t}  {tag}")

    elif kind == "layer_done":
        print(f"  → [Layer {ev['layer']}] found={ev['found']}")

    elif kind == "postprocess":
        print(f"\n[후처리 필터] {ev['filtered']}건 제거")

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
    parser.add_argument("--provider", choices=("local", "claude", "clovax"), default=None,
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
