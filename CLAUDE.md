# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

자격검정 **문제지(시험지) 오류 자동 탐지** PoC. HWP/HWPX/PDF 문제지를 업로드하면
오류를 **holistic 단일 LLM 호출**(문항당 1콜)로 검출하고, 검수자가 웹에서
확인/확정/반려할 수 있다. **내부망(폐쇄망) 프로덕션**을 전제로 하며, 외부
API(Claude) 의존성은 선택적 토글이다.

> 이력: 과거 3레이어 하이브리드(L0 규칙 + L1 그룹 + L2 per-type, 문항당 ~11콜,
> A01~A21 분류체계)를 cert-harness 외과적 v2 검출 코어로 **전면 대체**했다
> (문항당 1콜, 11-enum error_type, llama.cpp native grammar 출력강제).
> 경위는 `docs/harness_migration_plan.md`.

## 아키텍처 (큰 그림)

세 개의 독립 실행 단위가 하나의 파이프라인을 공유한다:

```
web/ (Next.js :3000)  ──HTTP/SSE──▶  api/ (FastAPI :8000)  ──import──▶  src/core/ (파이프라인 로직)
                                            │                                    │
                                       cert.db (SQLite)              local LLM(:8080) 또는 Claude API
```

### 단일 소스 원칙 (중요)

파이프라인 로직은 **`src/core/pipeline.py::run_pipeline()` 한 곳에만** 존재한다.
`run_pipeline(md_text, config, ...)`은 **제너레이터**로 `ProgressEvent`(dict)를 yield 한다.
호출자는 얇은 어댑터일 뿐 — 로직을 복제하지 않는다:

- **CLI** (`src/cli.py`): 이벤트를 콘솔 라인으로 출력
- **FastAPI** (`api/routers/sessions.py`): 이벤트를 그대로 JSON 직렬화해 SSE로 스트리밍
- `src/hybrid_run.py`는 `cli.main()`을 호출하는 back-compat shim일 뿐

`src/core/__init__.py`를 import 하면 `src/`가 `sys.path`에 등록되므로, core 모듈은
평면 모듈(`config`, `hwp_parser` 등)을 그대로 import 한다. core를 먼저 import 하는
순서를 깨지 말 것.

이벤트 스키마(`src/core/events.py`)는 camelCase이며 `web/lib/types.ts`가 이를 그대로
미러링한다. **한쪽을 바꾸면 반드시 양쪽을 함께 맞춘다.** 이벤트 종류:
`start(totalQ)` · `q_done(q, hasError, findings[])` · `done(totalFound, elapsed)` · `error`.
`findings[]` 항목도 camelCase: `{id, location, quote, errorType, reason, suggestion, confidence}`.

### holistic 검출 파이프라인

입력 흐름: `HWP/HWPX/PDF → (kordoc) Markdown → 문항 추출(## N.) → 문항별 holistic LLM 1콜(grammar 강제) → findings[] 정규화 → results.json`

- **검출 코어**: `prompts/holistic/review.md`(INSTRUCTION + `{{QUESTION_BLOCK}}`)
  + `prompts/_shared/output_schema.json`(11-enum findings 스키마). 레이어/규칙층/
  후처리 F필터는 **존재하지 않는다**.
- **출력 강제**: `pipeline.py::call_lm_studio()`가 `response_format=json_schema`를
  extra_body 로 요청 본문 최상위에 합류시킨다 → 서버(llama.cpp)가 GBNF 로 변환·강제.
  grammar 미지원 백엔드(Ollama/claude 등)는 `_extract_json()` 관용 파서로 폴백.
- **error_type 11-enum**: 맞춤법·띄어쓰기·문법비문·선택지누락·선택지중복·용어오류·
  사실오류·약어오기·정답유출·편집표시·기타.
- **운영조건**(cert-harness Run E 확정): temp=0, max_tokens=8000, 서버
  `--reasoning-budget 6000 --parallel 3`. 병렬은 `LLM_PARALLEL_WORKERS`(클라이언트)로.

### LLM 공급자 토글 (`src/config.py`)

`build_config(provider)`가 단일 cfg를 만들고 호출부가 `cfg['provider']`로 분기한다.
공급자는 **CLI `--provider` > `.env` `LLM_PROVIDER` > 기본 `local`** 순으로 결정.

- **`local`**: OpenAI 호환 서버(EXAONE / gpt-oss, llama.cpp·LM Studio·**Ollama**). 폐쇄망 기본.
  - **자동탐지**: `config.py::probe_local_backends()`가 후보 base_url 을 순서대로 프로브해
    첫 healthy 서버의 실제 모델·백엔드를 채택한다. 후보는 `LOCAL_BASE_URLS`(콤마) >
    `LOCAL_BASE_URL`(+공통 폴백) > 공통 후보(`11434` Ollama, `8080` llama.cpp, `1234` LM Studio).
  - **Ollama 인식**: `probe_ollama()`가 네이티브 `/api/ps`(메모리 로딩=실행중)를 우선,
    비면 `/api/tags`(설치됨)로 폴백해 모델을 잡는다(`backend="ollama"`, `loaded` 노출).
    Ollama 일 때는 llama.cpp 전용 extra_body(`cache_prompt`/`slot_id`)를 보내지 않는다.
- **`claude`**: Anthropic Claude Haiku. `ANTHROPIC_API_KEY` 필요(외부망 전용).
- **`clovax`**: Naver HyperCLOVA X(CLOVA Studio). OpenAI 호환 엔드포인트 +
  `CLOVASTUDIO_API_KEY`(`nv-` Bearer) 필요(외부망 전용). `local` 과 같은 OpenAI
  클라이언트 경로를 쓰되 llama.cpp 전용 extra_body 는 보내지 않는다.

### 프롬프트 (`prompts/`)

- `holistic/review.md` — 최종 검출 코어(INSTRUCTION + 분류 결정규칙 + quote 최소성),
  `{{QUESTION_BLOCK}}` 자리에 문항 텍스트 치환.
- `holistic/system.md` — holistic 검수자 시스템 프리앰블.
- `_shared/output_schema.json` — 11-enum findings 스키마(grammar 강제용, 메타키는
  `config.holistic_schema()`가 전송 전 제거).

**예시는 합성 예시여야 한다 — 특정 차수 실제 문항을 넣지 말 것.**

### 데이터 영속화 (`api/db.py`)

표준 라이브러리 SQLite(ORM 없음). 테이블: `sessions`, `questions`, `findings`
(오류 1건/행, PK `finding_id` = `"<q>-<index>"`), `review_actions`(검수 결과,
PK `finding_id` upsert). DB·결과 JSON은 `results/api/` 아래. 과거 A코드 데이터는
컷오버(단절) — `db._migrate()`가 레거시 `anomaly_results`·구 `review_actions`를 폐기.

## 개발 명령

### 백엔드 (FastAPI)
```powershell
pip install -r api/requirements.txt   # 또는 루트 requirements.txt
uvicorn api.main:app --reload --port 8000
```

### 프론트엔드 (Next.js — web/)
```powershell
cd web
npm run dev      # 개발 서버 :3000
npm run build
npm run start
npm run lint     # eslint
```

### 파이프라인 CLI (LLM 서버나 Claude 키 필요)
```powershell
python src/cli.py --input data/파일.md
python src/cli.py --input data/파일.md --q 13          # 13번 문항만
python src/cli.py --input data/파일.md --provider claude # .env 토글 덮어쓰기
python src/hwp_parser.py "data/파일.hwp"                # HWP→MD 단독 파싱
```

> 정식 테스트 스위트는 아직 없다. 회귀 검증은 합성 평가셋 + 파이프라인 재실행으로 한다
> (차수마다 문제가 바뀌므로 1차 데이터에 fit 하지 말 것).

## 환경 설정 (`.env`, 루트)

```env
LLM_PROVIDER=local                 # local | claude
LOCAL_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_XL  # holistic 프로덕션 모델
LLM_TEMPERATURE=0                  # holistic 결정성 (서버는 --reasoning-budget 6000)
LLM_MAX_TOKENS=8000
LLM_MAX_RETRIES=1                  # OpenAI 클라이언트 내부 재시도와 곱해지므로 주의
CLAUDE_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-...       # provider=claude 일 때만
CLOVASTUDIO_API_KEY=nv-...        # provider=clovax 일 때만 (CLOVA Studio)
CLOVASTUDIO_BASE_URL=https://clovastudio.stream.ntruss.com/v1/openai
CLOVASTUDIO_MODEL=HCX-005          # HCX-005 | HCX-007 | HCX-DASH-002 ...
```
`.env` 변경 후에는 **FastAPI를 재시작**해야 반영된다.

## 알려진 함정 (재발 방지)

- **grammar 출력강제는 llama.cpp 가정**: `response_format=json_schema`는 llama.cpp
  native grammar(GBNF) 백엔드에서만 안전. Ollama `format=schema` 단일호출은 붕괴
  이력이 있어 `_GRAMMAR_BACKENDS`(=`openai` 프로브)일 때만 전송하고 나머지는 폴백 파서.
- **서버 thinking 폭주 방지**: gemma4 는 `--reasoning-budget 6000` 없이 기동하면 일부
  문항에서 thinking 이 폭주해 JSON 이 잘린다. 서버 기동옵션을 빠뜨리지 말 것.
- **gpt-oss `>` 블록쿼트 버그**: `pipeline.py::sanitize()`가 블록쿼트를 `'(지문)'`으로
  치환한다(폴백 gpt-oss 모델 보호용). 제거하지 말 것 — gemma4 에는 영향 없음.
- **OpenAI 클라이언트 내부 재시도**: 기본 `max_retries=2`가 우리 재시도와 곱해져 과다
  호출. 클라이언트 생성 시 `max_retries=0`을 명시해야 한다.
- **KV 캐시 격리**: 문항 간 오염 방지로 `LLM_CACHE_PROMPT=false`, slot 격리 옵션 유지.
- **HWP 파서 Windows 호환**: node/kordoc 탐색이 리눅스 전용이면 Win에서 실패 →
  `shutil.which` + npx 캐시 glob으로 탐색.
- **web/는 Next.js 16**: `web/AGENTS.md` 참고. 학습 데이터와 API가 다를 수 있으니
  코드 작성 전 `node_modules/next/dist/docs/`의 해당 가이드를 확인.
- **다크 전용 UI**: `web/`는 Supabase Studio 컨셉의 다크모드 전용. `docs/DESIGN.md`의
  "화이트 캔버스"는 마케팅 기준이라 앱에는 미적용.

## 참고 문서

- `docs/harness_migration_plan.md` — holistic 전면 대체 전환 계획(설계·근거·리스크)
- `docs/hybrid_pipeline_개발보고서.md` — (이력) 3레이어 진화·실험 결과
- `docs/webapp_plan.md` — 웹앱 전체 설계(스택·엔드포인트·DB·UI)
- `prompts/README.md` — 프롬프트 카탈로그
