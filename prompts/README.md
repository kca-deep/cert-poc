# cert-poc — holistic 검출 프롬프트

자격검정(TOLIS) 문제지 검수용 **holistic 단일호출 검출 프롬프트**. 문항 1개를 한 번의
LLM 호출로 전 유형 검토하며, 출력은 llama.cpp native grammar 로 강제된다.

> 이력: 과거 `per-type/`(유형별 1콜) · `grouped/`·`hybrid/`(그룹 1콜) 체계를 cert-harness
> 외과적 v2 로 **전면 대체**했다. 경위는 `docs/harness_migration_plan.md`.

## 호출 단위
- **1 문항 = 1 콜** (전 유형 holistic). 과거 "문항×유형" 다중콜은 폐기.
- 외부 API 사용은 선택(claude/clovax). 폐쇄망 기본은 로컬 llama.cpp.

## 디렉터리 구조
```
prompts/
├── README.md              ← 이 파일
├── holistic/
│   ├── review.md          ← 검출 코어: INSTRUCTION + 분류 결정규칙 + {{QUESTION_BLOCK}}
│   └── system.md          ← holistic 검수자 시스템 프리앰블
└── _shared/
    ├── output_schema.json ← 11-enum findings 스키마 (grammar 강제용)
    └── _template.md       ← (참고) 신규 프롬프트 골격
```

## 출력 스키마 (`_shared/output_schema.json`)
응답은 **JSON 객체 1개**. `config.holistic_schema()`가 메타키를 제거하고
`response_format=json_schema`로 전달 → 서버가 GBNF 로 변환·강제한다.

```json
{
  "has_error": true,
  "findings": [
    {
      "location": "보기 ②",
      "quote": "외뷰",
      "error_type": "맞춤법",
      "reason": "'외뷰'는 '외부'의 오자",
      "suggestion": "외부",
      "confidence": "높음"
    }
  ]
}
```

- `error_type` 11-enum: `맞춤법 · 띄어쓰기 · 문법비문 · 선택지누락 · 선택지중복 ·
  용어오류 · 사실오류 · 약어오기 · 정답유출 · 편집표시 · 기타`
- `confidence`: `높음 | 보통 | 낮음`
- `quote`: 문항 원문 그대로 복사(지어내기 금지). 인용할 원문이 없으면 인접 원문 사용.
- 오류 없음: `has_error:false`, `findings:[]`

## 프롬프트 수정 규칙
- `{{QUESTION_BLOCK}}`: 파이프라인이 `## N.` 단위 문항 텍스트를 그대로 치환.
- **예시는 합성 예시여야 한다 — 특정 차수 실제 문항을 넣지 말 것.**
- `review.md` 의 분류 결정규칙과 `output_schema.json` 의 enum 은 **함께 맞춘다**.
  enum 을 바꾸면 `web/lib/types.ts`(ErrorType)·`web/lib/constants.ts`(ERROR_TYPES)도 동시 갱신.
