"""
core — 시험지 윤문 파이프라인의 단일 로직 소스.

CLI(src/cli.py)와 FastAPI(api/)가 모두 이 패키지를 import 한다.
로직은 여기 한 곳에만 존재하며, 부수효과(진행상황 출력)는 ProgressEvent를
yield 하는 방식으로 호출자에게 위임한다 → CLI는 print, API는 SSE로 변환.

기존 평면 모듈(code_checker, postprocess, config, hwp_parser)을 이동 없이
그대로 import 하기 위해, 패키지 로드 시 상위 src/ 디렉터리를 sys.path에 등록한다.
이렇게 하면 그 모듈들의 ROOT(=Path(__file__).parent.parent) 계산이 깨지지 않는다.
"""

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
