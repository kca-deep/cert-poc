# cert-poc API (FastAPI 백엔드 스켈레톤)

기존 Python 분석 파이프라인(`src/core/pipeline.py`)을 HTTP + SSE 로 감싸 Next.js
프론트엔드(`web/`)에 노출하는 백엔드. 현재는 **스켈레톤**: 엔드포인트 배선 완료,
SSE 스트리밍은 스텁으로 동작, 실 파이프라인 연결 자리만 표시.

## 실행

```bash
pip install -r api/requirements.txt
```

repo 루트에서:

```bash
uvicorn api.main:app --reload --port 8000
```

또는 `api/` 디렉토리에서:

```bash
cd api
uvicorn main:app --reload --port 8000
```

`config.py` 가 repo 루트를 찾아 `src/` 를 `sys.path` 에 주입하므로 어느 쪽에서
실행해도 `from core.pipeline import run_pipeline` 가 동작한다(파이프라인 준비 시).

## 엔드포인트 (web/lib/api.ts 와 경로 일치)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET  | `/health` | 헬스 체크 `{"status":"ok"}` |
| GET  | `/sessions` | 세션 목록 (`Session[]`) |
| GET  | `/sessions/{id}` | 세션 상세 (`SessionDetail`) or 404 |
| GET  | `/sessions/{id}/progress` | **SSE 진행률 스트림 (현재 STUB)** |
| POST | `/sessions` | 세션 생성 `{filename}` → `{"id": ...}` |
| POST | `/upload?mode=parse` | 파일 업로드 + 파싱 → `ParseResult` |

응답 JSON 은 `web/lib/types.ts` 의 인터페이스(`Session`, `SessionDetail`,
`ParseResult`)를 camelCase 로 그대로 미러링한다.

## SSE 이벤트 계약

이벤트 키는 `src/core/events.py` 의 **camelCase** 계약(`totalQ`, `typeCode`,
`totalFound` …)을 무변환으로 전달한다. (webapp_plan §5 의 snake_case 예시가
아니라 프론트 타입이 정본.) 시퀀스:

```
layer_start → q_layer0_done* → layer_done   (layer 0)
layer_start → q_type_done*   → layer_done   (layer 1)
layer_start → q_type_done*   → layer_done   (layer 2)
postprocess → done
```

> **주의:** `/sessions/{id}/progress` 는 현재 스텁 제너레이터가 그럴듯한 시퀀스를
> 방출한다. 실 파이프라인 배선 자리는 `api/routers/sessions.py` 의
> `_progress_source()` 안 `# TODO: replace stub ...` 주석이다.

## CORS

`http://localhost:3000`, `http://127.0.0.1:3000` (Next.js 개발 서버) 허용.

## 프론트엔드 연동

프론트엔드는 `NEXT_PUBLIC_USE_MOCK=false` 로 설정하면 mock 대신 이 API 를 호출한다
(`web/lib/api.ts`). 프론트는 상대경로 `/api/...` 로 호출하므로 Next 의 rewrite 로
이 서버(`:8000`)에 프록시하거나, 직접 베이스 URL 을 맞춘다.
