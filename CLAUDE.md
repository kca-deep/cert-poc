# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

자격검정 **문제지(시험지) 오류 자동 탐지** PoC. HWP/HWPX/PDF 문제지를 업로드하면
20종 오류 유형(A01~A21)을 3레이어 하이브리드 파이프라인으로 검출하고, 검수자가
웹에서 확인/확정/반려할 수 있다. **내부망(폐쇄망) 프로덕션**을 전제로 하며, 외부
API(Claude) 의존성은 선택적 토글이다.

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
평면 모듈(`config`, `code_checker`, `postprocess`)을 그대로 import 한다. core를 먼저
import 하는 순서를 깨지 말 것.

이벤트 스키마(`src/core/events.py`)는 camelCase이며 `web/lib/types.ts`가 이를 그대로
미러링한다. 한쪽을 바꾸면 반드시 양쪽을 함께 맞춘다.

### 3레이어 탐지 파이프라인

입력 흐름: `HWP/HWPX/PDF → (kordoc) Markdown → 문항 추출(## N.) → Layer 0/1/2 → 후처리 → merged_filtered.json`

| Layer | 방식 | 유형 | 비용 |
|-------|------|------|------|
| **0** | 규칙/정규식 (`src/code_checker.py`) | A01, A03, A13, A15, A17, A18 | LLM 0회 |
| **1** | 그룹 LLM (`prompts/hybrid/`) | G1[A04,A05,A06], G4[A09,A20], G5[A11,A14] | 그룹당 1회 |
| **2** | per-type LLM (`prompts/per-type/`) | A02, A07, A08, A10, A12, A16, A19, A21 | 유형당 1회 |

이후 `src/postprocess.py`의 후처리 필터(F1~F5)가 알려진 오탐을 제거한다(예: A06↔A02
경계, 뉴스 기사 `|` 기호 등). 레이어/그룹 구성은 `pipeline.py` 상단 `LAYER0_TYPES`,
`LAYER1_GROUPS`, `LAYER2_TYPES`에 정의돼 있다.

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

각 유형은 YAML frontmatter + 역할/정의/경계/체크절차/few-shot으로 구성되고
`{{QUESTION_BLOCK}}` 자리에 문항 텍스트가 치환된다. `per-type/`(개별), `grouped/`(실험),
`hybrid/`(최종 G1·G4·G5), `_shared/`(공통 preamble·output_schema.json).
**few-shot 예시는 합성 예시여야 한다 — 특정 차수 실제 문항을 넣지 말 것.**

### 데이터 영속화 (`api/db.py`)

표준 라이브러리 SQLite(ORM 없음). 테이블: `sessions`, `questions`, `anomaly_results`,
`review_actions`(검수 결과, 복합 PK upsert). DB·결과 JSON은 `results/api/` 아래.

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
LLM_MODEL=openai/gpt-oss-20b       # 축약형 'gpt-oss-20b' 금지(garbage) — 반드시 풀네임
LLM_MAX_RETRIES=1                  # OpenAI 클라이언트 내부 재시도와 곱해지므로 주의
CLAUDE_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-...       # provider=claude 일 때만
CLOVASTUDIO_API_KEY=nv-...        # provider=clovax 일 때만 (CLOVA Studio)
CLOVASTUDIO_BASE_URL=https://clovastudio.stream.ntruss.com/v1/openai
CLOVASTUDIO_MODEL=HCX-005          # HCX-005 | HCX-007 | HCX-DASH-002 ...
```
`.env` 변경 후에는 **FastAPI를 재시작**해야 반영된다.

## 알려진 함정 (재발 방지)

- **gpt-oss `>` 블록쿼트 버그**: 마크다운 블록쿼트가 garbage/무한 reasoning을 유발 →
  `pipeline.py::sanitize()`가 `'(지문)'`으로 치환한다. 제거하지 말 것.
- **OpenAI 클라이언트 내부 재시도**: 기본 `max_retries=2`가 우리 재시도와 곱해져 과다
  호출. 클라이언트 생성 시 `max_retries=0`을 명시해야 한다.
- **LM Studio 모델 ID**: 반드시 `openai/gpt-oss-20b` 풀네임.
- **KV 캐시 격리**: 문항 간 오염 방지로 `LLM_CACHE_PROMPT=false`, slot 격리 옵션 유지.
- **HWP 파서 Windows 호환**: node/kordoc 탐색이 리눅스 전용이면 Win에서 실패 →
  `shutil.which` + npx 캐시 glob으로 탐색.
- **web/는 Next.js 16**: `web/AGENTS.md` 참고. 학습 데이터와 API가 다를 수 있으니
  코드 작성 전 `node_modules/next/dist/docs/`의 해당 가이드를 확인.
- **다크 전용 UI**: `web/`는 Supabase Studio 컨셉의 다크모드 전용. `docs/DESIGN.md`의
  "화이트 캔버스"는 마케팅 기준이라 앱에는 미적용.

## 참고 문서

- `docs/hybrid_pipeline_개발보고서.md` — 파이프라인 진화·실험 결과(per-type→grouped→hybrid)
- `docs/webapp_plan.md` — 웹앱 전체 설계(스택·엔드포인트·DB·UI)
- `prompts/README.md` — 프롬프트 카탈로그
