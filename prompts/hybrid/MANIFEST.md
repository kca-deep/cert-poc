# Hybrid Pipeline — 프롬프트 매니페스트

데이터 기반 분석(per-type vs grouped-v2 3방향 비교)으로 도출된 최적 파이프라인.
21개 유형(A01~A21)을 탐지 안정성에 따라 3레이어로 분리.

---

## Layer 0 — 코드 처리 (LLM 불필요)

`src/code_checker.py`에서 규칙 기반 탐지.

| 유형 | 탐지 로직 | 근거 |
|------|---------|------|
| A01 보기 중복 | 선택지 텍스트 집합 비교 | grouped 100% 미탐, 코드 완전 대체 가능 |
| A03 보기개수 미달 | ①②③④ 기호 카운팅 | grouped 75% 미탐, 규칙 명확 |
| A13 문항번호 중복 | 중복 기호 탐지 | grouped 100% 미탐, 규칙 명확 |
| A15 보기 없음 | 기호 뒤 텍스트 공백 확인 | grouped 60% 미탐, 규칙 명확 |
| A17 지문 원문자 탈자 | ㉠㉡㉢㉣ 존재 여부 | grouped 100% 미탐, 규칙 명확 |
| A18 문장 전체 생략 | 지문 블록 패턴 | grouped 100% 미탐, 규칙 명확 |

---

## Layer 1 — 그룹 LLM (90 호출 / 30문항)

`prompts/hybrid/` 폴더의 그룹 프롬프트 사용.

| 파일 | 유형 | 일치율 | 근거 |
|------|------|-------|------|
| G1_typo_spelling.md | A04, A05, A06 | 67~100% | A02·A16 제거 후 안정화 |
| G4_legal_domain.md | A09, A20 | 100% | 법령명·조항 통합, A19 제거 |
| G5_editorial.md | A11, A14 | 안정 | A12 오분류 제거 후 안정화 |

**제외된 유형 및 이유:**
- A02, A16 → G1에서 제거: 경계 혼동(A04↔A02↔A16) → Layer 2로
- A19 → G4에서 제거: 100% 미탐 → Layer 2로
- A12 → G5에서 제거: A11과 오분류 빈발 → Layer 2로

---

## Layer 2 — per-type LLM (240 호출 / 30문항)

`prompts/per-type/` 폴더의 기존 단일 유형 프롬프트 사용.

| 유형 | 프롬프트 파일 | Layer 2 이유 |
|------|------------|------------|
| A02 오자 | A02_typo.md | grouped 67% 미탐, 경계 혼동 |
| A07 특수기호 누락 | A07_special_symbol_missing.md | 일치T=0, 완전 다른 케이스 탐지 |
| A08 매끄럽지 못한 문장 | A08_awkward_sentence.md | 일치T=0, 양쪽 불안정 |
| A10 오타+보기누락 | A10_typo_or_choice_missing.md | grouped 100% 미탐 |
| A12 낙서(유형2) | A12_graffiti_type2.md | A11과 오분류, 100% 미탐 |
| A16 탈자 | A16_char_dropout.md | grouped 83% 미탐 |
| A19 특수기호 누락(지문) | A19_special_symbol_missing.md | grouped 100% 미탐 |
| A21 잘못된 단어 | A21_wrong_word.md | 신규 유형(문맥상 오어휘), per-type 단독 |

---

## 호출 수 요약

| 레이어 | 방식 | 호출 수 | 절감 |
|--------|------|--------|------|
| Layer 0 | 코드 | 0 | — |
| Layer 1 | 그룹 LLM | 90 | — |
| Layer 2 | per-type LLM | 240 | — |
| **합계** | | **330** | **약 48% 절감** |
| 기존 per-type 전체 | | 630 | 기준 |
