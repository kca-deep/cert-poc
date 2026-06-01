"""
hybrid_run.py — 하위 호환 shim (back-compat shim).

★ 파이프라인 로직은 이제 core/pipeline.py 에 단일 소스로 존재한다.
  콘솔 출력/CLI 어댑터는 cli.py 가 담당한다.

이 파일은 기존 `python src/hybrid_run.py --input ...` 명령이 그대로 동작하도록
cli.main() 으로 위임하는 얇은 진입점일 뿐이다. 로직을 중복 정의하지 않는다.
"""

import sys
from pathlib import Path

# src/ 를 import 경로에 추가해 cli / core 를 찾을 수 있게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli import main  # noqa: E402

if __name__ == "__main__":
    main()
