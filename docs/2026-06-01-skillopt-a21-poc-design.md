# SkillOpt식 A21 프롬프트 자동개선 PoC 설계안

> 자격검정 검수 파이프라인의 A21(단어 교체 오류) 프롬프트를, SkillOpt(2026)의
> "검증 게이트 기반 텍스트 최적화" 방식으로 **과탐(오탐) 자동 감소**시키는 PoC 설계.
> **프로덕션 무영향**이 1순위. 작성일 2026-06-01.
> 참고: [SkillOpt arXiv](https://arxiv.org/abs/2605.23904) · 관련 메모리 [[feedback_haiku_false_positives]] [[feedback_cohort_generalization]]

---

## 0. 배경 — 현재 구조 (확인된 사실)

| 항목 | 현황 |
|------|------|
| A21 프롬프트 | `prompts/per-type/A21_wrong_word.md` (frontmatter + 정의/경계/점검절차/합성 few-shot + `{{QUESTION_BLOCK}}`) |
| 프롬프트 로딩 | `src/core/pipeline.py` 가 `PROMPT_DIR/per-type/{code}_*.md` 를 **glob 자동탐색** → 이 폴더에 파일 추가 시 프로덕션 오염 ⚠️ |
| 기존 채점 인프라 | `src/verify.py`: `data/정보보호개요_O.md`(정답본) vs `_X.md`(오류본) char-diff → (Q,A)별 found/위치 일치 매트릭스. 단 **1차 20문항(A01~A20) fit, A21 미포함** |
| A21 평가셋 | **없음**. few-shot 은 합성. 실시험 O/X 는 외부 유출 금지 자료 |
| 알려진 문제 | Haiku 기준 A07/A21/A14 판단형에 과탐 집중(오탐 ~29%) |

---

## 1. 목표 / 비목표

**목표**: A21 프롬프트의 **과탐을 자동 감소시키되 실제 검출률 유지**. 사람이 하던
"프롬프트 수정 → 평가셋 확인 → 채택" 루프를 검증 게이트로 반자동화.

**비목표**: 프로덕션 프롬프트/코드/파이프라인 변경, 모델 파인튜닝, A21 외 유형,
자동 배포. PoC 는 **후보 프롬프트 + 측정 리포트만** 산출하고 적용은 사람이 수동.

---

## 2. 프로덕션 격리 원칙 (1순위)

| 격리 대상 | 방법 |
|---|---|
| 프롬프트 | 후보는 **`experiments/skillopt-a21/candidates/`** 에만. `prompts/per-type/` 에 **파일 추가 금지**(pipeline glob 오염). 후보는 명시적 절대경로 로드. |
| 코드 | `src/core`, `api/`, `web/`, `prompts/`, `results/` **불변**. PoC 코드는 전부 `experiments/`. 기존 모듈은 **읽기전용 import**(LLM 호출·sanitize·스키마 검증 재사용). import 곤란 시 단일콜 경로만 최소 복제. |
| 데이터 | 평가셋 **100% 합성** → 외부 유출 규정 무관, optimizer 에 Claude 사용 가능. |
| 산출물 | 로그·후보·리포트 모두 `experiments/skillopt-a21/runs/`. git 별도 브랜치 또는 untracked. |
| 적용 | PoC 는 prod 에 절대 안 씀. 승격은 "후보 vs 현행 unified diff" 를 사람이 리뷰 후 수동 반영 + 정식 회귀. |

> 핵심: pipeline 이 `per-type/A21_*.md` 를 glob 하므로 후보를 그 폴더에 두면 안 된다.
> PoC 러너는 후보 텍스트를 경로로 직접 읽어 `{{QUESTION_BLOCK}}` 치환 → LLM 호출하는
> **독립 단일콜 경로**(프로덕션 라우팅 우회)를 쓴다.

---

## 3. 평가셋 설계 (`experiments/skillopt-a21/dataset/`)

오탐 문제이므로 **음성 케이스가 양성만큼 중요**.

- **양성(A21 주입) ~20개**: 반대 의미 교체("최대한"↔"최소한"), 원칙 반전("변경"↔"금지"),
  논리 불가 단어. 각 항목 `location` + `gold_suggested`(정답 단어) 라벨.
- **하드 음성(보고 금지) ~25개**: A21 로 오인하기 쉬운 정상/타유형 —
  A08(어색하지만 단정 불가), A02(자모 오자=A21 아님), 정상 정답 문장,
  시험지 "오답 선택지"(내용상 틀리나 A21 아님). `found:false` 라벨.
- **분할**: train(few-shot/관찰) / **val(채택 게이트)** / **test(최종 보고)**.
  test 는 **다른 생성 시드·템플릿**으로 만들어 차수 일반화 대용([[feedback_cohort_generalization]]),
  val 과적합 방지.
- 항목 형식: `{id, question_block, label:{found, location?, gold_suggested?}, kind:"pos|hard_neg", split}`.

---

## 4. 채점기 (`scorer.py`)

`verify.py` 의 found/위치 일치 로직 재사용 + **라벨 평가셋·음성 포함**으로 확장.

- 양성: `found=true` ∧ `location` 일치 ∧ `suggested` 정규화 후 `gold_suggested` 일치 → **TP**, 아니면 FN.
- 음성: `found=false` → TN, `found=true` → **FP**(=오탐, 감축 대상).
- 지표: **Precision, Recall, F0.5**(정밀도 가중 — 과탐 억제 목적).
- **목적함수 = F0.5**, **제약 = Recall ≥ baseline_recall − ε**(검출률 하락 금지 가드).

---

## 5. 최적화 루프 (SkillOpt 매핑)

| SkillOpt | 본 PoC |
|---|---|
| Skill document | A21 후보 프롬프트 1개(현행 복사본에서 출발) |
| Rollout | 후보로 train+val 항목을 **로컬 모델**(prod 동일, 충실도) 단일콜 실행 |
| 채점 | §4 채점기로 val F0.5 + recall |
| Optimizer | **별도 모델(Claude)** 이 실패 사례(FP/FN)를 보고 add/delete/replace 편집 제안 |
| 편집 예산 | 스텝당 최대 N개(예 2~3) = 텍스트 학습률 |
| 검증 게이트 | **val F0.5 ↑ AND recall 제약 충족 시에만 채택**, 아니면 롤백 |
| 거절 버퍼 | 거절된 편집 요약을 다음 제안에 negative feedback 첨부 |
| 종료 | 개선 없는 스텝 K회 연속 또는 최대 스텝 |

```text
cand = copy(prod_A21_prompt); best = score_val(cand)
reject_buf = []
while steps < MAX and no_improve < K:
    fails = sample_failures(cand, train ∪ val)        # FP/FN 예시
    edits = optimizer_propose(cand, fails, reject_buf, budget=N)
    trial = apply(cand, edits)
    s = score_val(trial)                              # held-out val
    if s.f05 > best.f05 and s.recall >= recall_floor:
        cand, best = trial, s; no_improve = 0
    else:
        reject_buf.append(summarize(edits, s)); no_improve += 1
report = score_test(cand)                              # 최종, 미사용 split
emit unified_diff(prod_A21_prompt, cand), report
```

---

## 6. 디렉토리 구조

```text
experiments/skillopt-a21/        # 전부 prod 밖, 격리
├── README.md                    # 실행법·격리원칙
├── dataset/{train,val,test}.jsonl
├── candidates/                  # A21 후보 .md (prod per-type/ 아님)
├── runs/<ts>/                   # 스텝별 후보·점수·로그·거절버퍼
├── scorer.py  runner.py  optimizer.py  loop.py
└── report.md                    # 베이스라인 vs 최종 + diff
```

---

## 7. 실행 단계 (Phase)

1. **평가셋 구축 + 사람 라벨 검수** (채점 신뢰도 전제 — [[feedback_haiku_false_positives]]).
2. **베이스라인 측정**: 현행 A21 프롬프트로 val/test 점수 기록(기준선).
3. **루프 1회전**: 편집 예산 2, 5~10 스텝 소규모 검증.
4. **리포트**: test 기준 F0.5/precision/recall 변화 + unified diff.
5. **사람 결정**: 채택 시 수동 prod 반영 → 정식 회귀(verify 매트릭스) → 커밋.

---

## 8. 승격(promotion) 기준

- test split 에서 **precision 유의 상승**, **recall ≥ 기준선 − ε**, 차수-대용 test 에서도 유지.
- 산출물은 diff 뿐 — **사람이 검토·적용**. 자동 쓰기 없음.

---

## 9. 리스크 / 완화

| 리스크 | 완화 |
|---|---|
| 로컬 모델 비결정성 | temperature 고정, 항목당 다중 롤아웃 다수결, `max_retries=0` ([[feedback_openai_client_retries]]) |
| gpt-oss garbage/블록쿼트 | 단일콜에 `sanitize()` 필수 ([[feedback_gpt_oss_blockquote_bug]]), 모델ID `openai/gpt-oss-20b` 정확히 ([[reference_lmstudio_model_id]]) |
| val 과적합 | test 분리 + 작은 편집 예산 + 하드 음성 |
| 차수 fit | test 를 다른 합성 시드로 ([[feedback_cohort_generalization]]) |
| 채점기 오류 | 라벨 사람 검수, 정규화 규칙 명시 |

---

## 10. 결정 필요 항목

1. **Optimizer 모델**: Claude(편집 품질↑, 합성데이터라 안전) vs 로컬(완전 오프라인). → 권장 **Claude Haiku**.
2. **Target 모델**: prod 동일 로컬 고정 권장(프롬프트가 그 모델에 튜닝). Haiku 오탐을 직접 잡으려면 target=Haiku 도 가능.
3. **평가셋 규모**: 권장 양성20/음성25(총 ~45). 확대 여부.
4. **목적함수**: F0.5(정밀도 가중) vs F1.
