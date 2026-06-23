# 하네스 전면 대체 전환 계획 (Harness Migration Plan)

> 전제: **하이브리드 없이**, cert-harness 최종본(외과적 v2 프롬프트 + native grammar)으로
> cert-poc의 **3레이어 파이프라인 전체를 대체**한다(L0 규칙층 포함 폐기).
> 본 문서는 설계/계획 문서이며 코드 변경을 포함하지 않는다.
>
> 근거 데이터: 동일 문서(V2 30문항) 기준 하네스 vs 파이프라인 비교 및 프롬프트 회귀 검증
> (`cert-harness/experiments/v2_30q_*`). 관련 사전 분석: `docs/hybrid_pipeline_개발보고서.md`,
> `docs/webapp_plan.md`, `cert-harness/STATUS.md`.

---

## 1. 목표와 범위

| | 내용 |
|---|---|
| **목표** | 문항당 ~11회 LLM 호출(L0 규칙6 + L1 그룹3 + L2 per-type8)을 **문항당 1회 holistic 호출**로 대체 |
| **검출 코어** | cert-harness 외과적 v2 `INSTRUCTION` + `SCHEMA`(9-enum) + llama.cpp native grammar 강제 |
| **범위(In)** | `src/core/pipeline.py`, 프롬프트, 출력 스키마/강제, `events.py`, 데이터모델(DB), 웹 UI, 후처리, 규칙층 |
| **범위(Out)** | 모델 학습/튜닝, 새 차수 데이터 수집, 검수 정책 자체 |
| **비전제** | 규칙층·A코드 분류체계 **존속 가정 없음**(전면 대체) |

### 1.1 전면 대체가 가능해진 근거
프롬프트 개선(v2)이 **규칙층이 담당하던 구조검출을 holistic으로 흡수**함을 30문항 회귀로 확인:

| 구조 오류 | 기존 담당(규칙) | v2 holistic 검출 |
|---|---|---|
| 보기 누락 | A03 | ✅ Q3 |
| 보기 번호 중복 | A13 | ✅ Q13 |
| 빈 보기 | A15 | ✅ Q15 |
| 정답 유출 | (규칙 A14) | ✅ Q14 (프롬프트 체크리스트) |
| 편집 잔여태그 | A11/A12 | ✅ Q12 |

→ 규칙층 폐기의 **전제는 상당부 충족**. 단 "결정성 보장"은 잃는다(→ §7 리스크).

---

## 2. 타깃 아키텍처 (Before → After)

```
[Before] HWP/PDF → MD → 문항추출
  → L0 규칙(code_checker) ┐
  → L1 그룹LLM(G1·G4·G5)  ├─ 문항×유형 ~11콜 → merge → postprocess(F1~F5) → merged_filtered.json
  → L2 per-type LLM(8유형)┘                                   (A01~A21 분류체계)

[After]  HWP/PDF → MD → 문항추출
  → holistic 1콜(grammar 강제) → findings[] → (경량 정리) → results.json
                                              (9-enum + 정답유출/편집표시 확장)
```

- 호출 수: **11 → 1** (문항당). 실측 속도 ≈ **5배**(30문항 1:36:17 → 19:52).
- 코드 표면: 레이어 분기·F필터·규칙 **삭제**로 오히려 단순화.

---

## 3. 검출 코어 (확정 자산)

cert-harness 외과적 v2가 그대로 프로덕션 코어. 핵심 구성:

1. **INSTRUCTION** — 검토 대상(맞춤법·띄어쓰기·문법비문·용어·사실·약어·선택지 누락/중복)
   + 구조 체크리스트(정답유출·편집잔여태그·정답정합·원문자중복)
   + 분류 결정규칙(약어오기/선택지중복/용어오류 라우팅)
   + quote 최소성/공란 처리 + "여러 오류 각각 보고(누락 금지)".
2. **SCHEMA** — `{has_error, findings[{location, quote, error_type, reason, suggestion, confidence}]}`,
   `error_type` 9-enum(+ §6 확장).
3. **강제** — `response_format=json_schema` → 서버 GBNF 변환(디코딩 토큰 마스킹).
4. **운영조건** — `--reasoning-budget 6000`, `max_tokens 8000`, `temp 0`, `--parallel 3`.

> 회귀 실적(외과 v2): has_error 26/30, findings 44, quote **100%**, 폭주 0, 기타 과분류 0.

---

## 4. 컴포넌트별 변경 맵

| 구분 | 대상 | 작업 | 규모 |
|---|---|---|---|
| **삭제** | `src/code_checker.py` | L0 규칙 전체 폐기 | 中 |
| | `prompts/per-type/*`, `prompts/hybrid/*`, `prompts/grouped/*` | per-type/그룹 프롬프트 폐기 | 中 |
| | `src/postprocess.py` F1~F5 | 유형쌍 오탐필터 폐기(A코드 소멸로 무의미) | 中 |
| | `pipeline.py` `LAYER0/1/2`·`_run_layer0/1/2` | 레이어 분기 제거 | 中 |
| **대체** | `pipeline.py::run_pipeline` | 문항당 holistic 1콜 루프 + `_merge` 단순화 | 大 |
| | `prompts/_shared/` | holistic INSTRUCTION + SCHEMA 단일화 | 中 |
| | `prompts/_shared/output_schema.json` | per-type → holistic findings 스키마 | 中 |
| | `src/core/events.py` ↔ `web/lib/types.ts` | 유형단위 → 문항단위 이벤트(미러 동시) | 中 |
| | `api/db.py` | `anomaly_results`(type_code PK) → `findings`(finding_id) | 大 |
| | 웹 매트릭스/QuestionList/AnomalyCard/PipelineProgress | findings 뷰 + 진행률 문항단위 | 大 |
| **신규** | 출력강제 계층 | `response_format=json_schema` + 공급자별 분기 + 폴백 파서 | 中 |
| | `error_type` enum 확장 | `정답유출`/`편집표시` 추가(라벨 드리프트 해소) | 小 |
| | 결정성/회귀 검증 하니스 | determinism mode + GT 자동채점 + 회귀 게이트 | 中 |
| **유지** | `src/config.py` 골격, `call_with_retry` 외피, 서버 운영조건 | 공급자 토글 유지 | 小 |

---

## 5. 데이터모델 · 이벤트 · 웹 이행 (최대 표면)

### 5.1 DB (`api/db.py`)
- `anomaly_results`(복합 PK `question_number+type_code`, 유형별 1행)
  → **`findings`**(PK `finding_id`, `question_number` FK, `location/quote/error_type/reason/suggestion/confidence`).
- `review_actions`가 `type_code` 의존 복합 PK였음 → **`finding_id` 기준 재설계**(검수 확정/반려가 finding 단위).
- 마이그레이션: 기존 세션은 A코드→9-enum **역매핑** 또는 **신규 세션부터 적용(컷오버)** 중 택1(§9 미결정).

### 5.2 이벤트 (`events.py` ↔ `web/lib/types.ts` 미러)
- 폐기: `q_type_done(layer, type_code, found, confidence)`, `layer_done`, layer 개념.
- 신설: **`q_done(question_number, findings[], elapsedSeconds)`**.
- SSE(`api/routers/sessions.py`)는 직렬화만 하므로 코드 변경 작지만 **계약 변경**이므로 양쪽 검증.
- ⚠️ camelCase 미러 규칙(CLAUDE.md): events.py와 types.ts **반드시 동시 수정**.

### 5.3 웹
- 20-유형 매트릭스(`ANOMALY_TYPES`/`ANOMALY_TYPE_ORDER` 카탈로그) → **findings 리스트 뷰 + 9-enum(+확장) 칩**.
- `QuestionList` 유형 틴트, `AnomalyCard`, `PipelineProgress`(레이어/유형 그리드) 개편.
- 진행률 UI: 레이어/유형 진척 → **문항 진척(N/총문항)**. (앞서 mm:ss로 고친 `PipelineProgress`도 문항단위로 재작성)

---

## 6. 출력 강제 계층 (전환의 핵심)

> 현 파이프라인은 출력 스키마를 **정의만 하고 강제 안 함**(프롬프트 참조 + `_extract_json` 관용 파싱).
> per-type가 작아 버텼으나, holistic은 출력이 커 **grammar 강제 없이는 붕괴**(STATUS.md 실험②③ 0/13 → ④⑤ grammar로 10/10).

1. `pipeline.py` 호출에 `response_format={type:"json_schema", json_schema:{schema: SCHEMA}}` 추가.
2. `error_type` enum 확장: 기존 9종 + **`정답유출`, `편집표시`**(구조오류 라벨 드리프트 해소).
3. 관용 파서(`_extract_json`/`_coerce`)·postprocess 출력방어는 grammar가 보장하면 **역할 축소**(폴백으로만 잔존).

### 6.1 공급자별 강제 메커니즘 (이식성)
| provider | 강제 방식 | 비고 |
|---|---|---|
| local **llama.cpp** | native grammar(json_schema→GBNF) | ✅ 검증됨(현 서버) |
| local **Ollama** | `format=schema` | ⚠️ **붕괴 이력**(STATUS.md) → 백엔드 감지 분기·폴백 |
| **claude** | tool-use(forced tool) | GBNF 미지원 |
| **clovax** | structured/json 모드 | GBNF 미지원 |

→ **공급자별 출력강제 분기 + grammar 미지원 공급자용 관용 파서 폴백**은 필수 신규 작업.

---

## 7. 전면 대체 특유 리스크 · 완화

| # | 리스크 | 완화 | 잔여 |
|---|---|---|---|
| R1 | **결정성 보장 상실** — 규칙(정규식)은 보기개수·번호중복을 100% 검출, LLM은 확률적. temp=0이나 병렬슬롯 비결정성(Q9 변동) | 결정성 평가모드(workers=1) 회귀 고정 · 구조검출 체크리스트 강제 · N회 합의 | 단순 구조오류도 확률적 — 극소수 결정 룰을 '검증 게이트'로 남길지 결정 필요 |
| R2 | **공급자 이식성** — grammar는 llama.cpp만 안전 | 백엔드별 강제 분기 + 폴백 파서 | 폐쇄망이 llama.cpp 미보장 시 전면대체 **보류** |
| R3 | **라벨 드리프트** — 정답유출이 '선택지누락'으로 | enum 확장(§6.2) | 9-enum 자체의 표현력 한계 |
| R4 | **A코드 자산 단절** — 통계/차수비교가 A01~A21 기반 | 매핑표 or 컷오버 시점 명시 | 과거 데이터와 직접 비교 단절 |
| R5 | **검출 변동성 = 검수 신뢰** — 규칙 안전망 없이 LLM 단독, 미검출=누락 | GT 자동채점 + 회귀 게이트 상시 감시 | Q9형 경계 케이스 잔존 |

---

## 8. 검증 계획

매 단계 후 **동일 30문항 회귀**(가능하면 합성 평가셋 병행):

- **정확도**: GT(정답키) 기준 문항별 P/R/F1, 오탐/미탐 리스트
- **충실도**: quote 일치율(목표 100%)
- **안정성**: thinking 길이·`finish=length` 폭주율(0 유지), 파싱 성공률
- **분류 건전성**: error_type 분포(기타 비율 급증 = 회귀 신호), confidence 분포
- **결정성**: 동일 입력 N회 반복의 검출 분산
- **컷오버 기준**: 원본(현 파이프라인) 대비 **검출 비열세** + **구조검출 미스 0** + 폭주 0

> 교훈(이번 세션): "광범위 개선" 버전이 findings 45→27·기타 1→22로 **붕괴했으나 요약(quote 100%)만 보면 좋아 보였다**. → 회귀 게이트(분포 메트릭)가 없으면 붕괴를 놓친다.

---

## 9. 단계별 이행 (컷오버형)

| 단계 | 내용 | 산출/게이트 |
|---|---|---|
| **P0** | 출력계약 확정 — holistic SCHEMA(+enum 확장), 공급자별 grammar 강제 PoC, GT 정답키 구조화 | 강제 PoC 통과 + GT 채점 동작 |
| **P1** | 코어 교체 — `run_pipeline` holistic화, 출력강제/폴백, `events.py` 신계약. **CLI 어댑터로 먼저 검증**(웹 무관) | 30문항 회귀 ≥ 원본 |
| **P2** | 데이터/이벤트 — `db.py` findings 스키마 + 마이그레이션, `types.ts` 미러, SSE 검증 | 라운드트립 + 검수 저장 동작 |
| **P3** | 웹 — 매트릭스→findings 뷰, 진행률 문항단위, 검수 finding 단위 | UI 회귀 |
| **P4** | 정리 — `code_checker`/per-type/hybrid/`postprocess` 삭제, 문서·런처 운영조건 갱신 | 데드코드 0 |

---

## 10. 결정이 필요한 미결정 사항

1. **결정적 룰 완전폐기 vs 극소수 검증게이트 잔존** — 보기개수/번호중복 같은 100%-검출 가능 항목을 LLM에만 맡길지, 최소 룰을 안전망으로 남길지(엄밀히는 "전면 대체"의 예외).
2. **과거 A코드 데이터** — 9-enum 매핑 보존 vs 컷오버 단절.
3. **폐쇄망 백엔드 보장** — 프로덕션 서버가 llama.cpp native grammar를 보장하는가. 아니면(Ollama 등) 전면대체 보류 또는 공급자 한정.
4. **라벨 체계** — 9-enum + 확장으로 충분한가, 아니면 검수/리포트 요구에 맞춘 별도 category 축이 필요한가.

---

## 11. 한 줄 요약

> 전면 대체의 본질은 **"holistic 검출 코어(v2) + grammar 출력강제"를 cert-poc의 데이터모델·이벤트·공급자·웹 골격에 이식하면서, 규칙층의 결정성을 프롬프트·검증 하니스로 대체"** 하는 것이다.
> 검출력·속도(5배)·코드 단순화를 얻는 대신 **결정성 보장·A코드 자산·공급자 이식성**을 리스크로 떠안으며, 이를 **GT 자동채점 + 회귀 게이트 + 결정성 모드**로 방어하는 것이 성패를 가른다.
