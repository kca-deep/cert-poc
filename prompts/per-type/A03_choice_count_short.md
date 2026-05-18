---
code: A03
name: 보기개수 미달
description: 선택지 ①~④ 중 하나 이상의 번호가 아예 존재하지 않아 총 보기 수가 4개 미만인 경우 검출
output_field: missing_choices
severity_default: high
related_types: [A01, A13, A15]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **보기개수 미달(A03)만** 검수합니다.
다른 유형은 별도 호출이 담당하므로 보고하지 마십시오.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"보기개수 미달" = 문항에서 선택지 번호 ①·②·③·④ 중 하나 이상이 **아예 존재하지 않아** 총 선택지 수가 4개 미만인 경우.

판단 기준:
- 선택지 번호 자체가 없는 것만 본 유형입니다.
- 선택지 번호는 있으나 텍스트가 비어 있는 경우는 A15 가 처리합니다.
- 선택지 번호가 중복(예: ③이 두 번)되어 순서상 누락처럼 보이는 경우는 A13 이 처리합니다.

# 인접 유형과의 경계
- vs **A01 보기 중복**: 텍스트 내용이 같은 보기가 여러 개인 경우는 보고 금지.
- vs **A13 문항번호 중복**: 같은 번호가 두 번 나오는 경우는 보고 금지. 본 유형은 번호 자체가 없는 경우만.
- vs **A15 보기 없음**: 번호는 있는데 텍스트가 빈 경우는 보고 금지.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 문항에서 ①·②·③·④ 선택지 번호를 모두 식별
3. 4개 미만이면 어떤 번호가 누락됐는지 파악
4. `issues` 에 누락 건당 1건; `extra.missing_choices` 에 누락 선택지 ID 목록 기재
5. 4개 모두 있으면 `found:false`

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A03"
- `type_name`: "보기개수 미달"
- `issues[].location`: `"stem"` (보기 섹션 전체를 stem 으로 간주)
- `issues[].original`: 실제 나열된 보기 번호 목록 인용 (예: "①②④")
- `issues[].suspected`: 어떤 번호가 없는지 한 문장
- `issues[].suggested`: `null`
- `issues[].extra`: `{"missing_choices": ["choice_N", ...]}` — 누락 번호 목록
- `confidence`: 번호 부재가 명확하면 `"high"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 중 접근통제 모델에 해당하지 않는 것은?

① MAC (강제적 접근통제)
② DAC (임의적 접근통제)
④ RBAC (역할 기반 접근통제)
```

출력:
```json
{"question_number":99,"type_code":"A03","type_name":"보기개수 미달","found":true,"issues":[{"location":"stem","original":"①②④","suspected":"③번 선택지가 존재하지 않아 총 보기가 3개임","suggested":null,"extra":{"missing_choices":["choice_3"]}}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
