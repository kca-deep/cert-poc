# cert-poc — 유형별 윤문 프롬프트

정보보호능력검정(TOLIS) 시험 문제지의 **유형별 검수/윤문 LLM 프롬프트** 모음입니다.
1차 진행 범위는 **정보보호 개요 카탈로그 A01~A20** 입니다.

## 호출 단위
- **1 문항 × 1 유형 = 1 콜**
- 정보보호 개요 20문항 × 20유형 = **400 콜** (LM Studio `openai/gpt-oss-20b` 로컬)
- 한 콜은 단 하나의 유형만 점검하며, 다른 유형 결함은 별도 콜에서 검출합니다.
- 외부 API 사용 금지(시험 문제는 외부 유출 금지 자료). 모든 호출은 로컬 LM Studio.

## 디렉터리 구조
```
prompts/
├── README.md              ← 이 파일
├── _shared/
│   ├── system_preamble.md ← 모든 유형 공통 시스템 프리앰블 (역할/언어/금지/출력형식)
│   ├── output_schema.json ← 응답 JSON Schema (러너의 검증/머지 기반)
│   └── _template.md       ← 신규 유형 추가 시 복제할 골격
└── per-type/
    ├── A01_choice_duplicate.md
    ├── A02_typo.md
    ├── A03_choice_count_short.md
    ├── A04_spelling.md
    ├── A05_typo_english.md
    ├── A06_spacing.md
    ├── A07_special_symbol_missing.md
    ├── A08_awkward_sentence.md
    ├── A09_wrong_law_name.md
    ├── A10_typo_or_choice_missing.md
    ├── A11_graffiti_type1.md
    ├── A12_graffiti_type2.md
    ├── A13_question_number_duplicate.md
    ├── A14_answer_leak.md
    ├── A15_choice_text_missing.md
    ├── A16_char_dropout.md
    ├── A17_passage_marker_dropout.md
    ├── A18_passage_whole_missing.md
    ├── A19_special_symbol_missing.md
    └── A20_wrong_law_article.md
```

## 파일명 규칙
- `A{NN}_{english_slug}.md` — 코드 + 영문 슬러그(snake_case)
- 한글 파일명은 일부 도구·CI에서 깨질 위험이 있어 금지

## 프롬프트 파일 구조
각 유형 파일은 다음 섹션을 포함합니다 (`_shared/_template.md` 참조).

```
---
code: A02
name: 오자
description: 한글 음절 단위 오자 검출
output_field: typo
severity_default: medium
related_types: [A04, A05, A16]
---

# 역할
# 정의
# 인접 유형과의 경계
# 점검 절차
# 출력
# Few-shot (1개)
# 입력 문항
{{QUESTION_BLOCK}}
```

- `{{QUESTION_BLOCK}}`: 러너가 `## N.` 단위 문항 텍스트를 그대로 치환.
- YAML frontmatter: 러너가 메타만 파싱해 호출 라우팅·결과 라벨링에 사용.

## 출력 JSON 스키마
응답은 **JSON 객체 1개** 만 (코드펜스·설명·인삿말 금지). `_shared/output_schema.json` 참조.

```json
{
  "question_number": 1,
  "type_code": "A02",
  "type_name": "오자",
  "found": true,
  "issues": [
    {
      "location": "choice_1",
      "original": "노출되지 앙게",
      "suspected": "'앙게'는 '않게'의 음절 오자",
      "suggested": "노출되지 않게"
    }
  ],
  "confidence": "high"
}
```

- `location` enum: `stem | passage | choice_1 | choice_2 | choice_3 | choice_4`
- `issues[].extra` (선택): 유형별 보조 정보 (예: A01 의 `duplicate_with`, A03 의 `missing_choices`)
- 결함 없음: `found:false`, `issues:[]`, `confidence` 도 `low` 가능

## 신규 유형 추가 절차
1. `_shared/_template.md` 복제 → `per-type/A{NN}_<slug>.md`
2. frontmatter 채우기 (code·name·description·related_types)
3. 정의·경계·점검 절차·few-shot 작성
4. dry-run 1~2 문항 호출로 JSON 안정성 확인
5. 필요 시 인접 유형 프롬프트의 `related_types` 와 "vs Axx" 절을 상호 갱신

## 진행 상태 (1차)
- [x] `_shared/system_preamble.md`
- [x] `_shared/output_schema.json`
- [x] `_shared/_template.md`
- [ ] 시범 5개: A01·A02·A04·A06·A14
- [ ] 잔여 15개
- [ ] 러너·머저·평가기 (`src/`)
