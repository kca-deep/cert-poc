---
code: A18
name: 문장 전체 생략
description: 문항이 지문(passage)을 참조하나 지문 블록 자체가 통째로 없는 경우 검출
output_field: passage_missing
severity_default: high
related_types: [A16, A17]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **문장 전체 생략(A18)만** 검수합니다.
부분적 탈자(A16)·원문자 탈자(A17) 등은 별도 호출이 담당합니다.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"문장 전체 생략" = 문항의 본문(stem)이 지문이나 예시 문장을 제시할 것을 시사하지만 **지문(passage) 블록 자체가 아예 없는** 경우.
- 예: "다음 문장이 설명하는 기관의 이름은?" 이라고 했으나 아래에 아무런 지문이 없음
- 지문이 있어야 할 자리에 선택지가 바로 나오는 경우

판단 기준:
- 문제 본문에 '다음 문장', '다음 설명', '다음 지문', '다음 신문기사', '다음은 ○○에 대한 설명' 등의 표현이 있는데 지문 블록이 없으면 해당.
- 지문이 일부 잘린 경우(A16)와 달리, 본 유형은 지문이 **완전히** 없는 경우만.

# 인접 유형과의 경계
- vs **A16 탈자**: 지문 내 글자 일부가 빠진 경우는 보고 금지.
- vs **A17 원문자 탈자**: 지문 내 원문자가 빠진 경우는 보고 금지.
- 지문이 원래 없는 단순 질문형 문항에서 `found:false` 를 반환합니다.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 문제 본문(stem)에서 '다음 문장', '다음 설명', '다음 ○○' 등 지문 제시를 시사하는 표현 확인
3. 지문 제시 표현이 있는 경우, 실제 지문 블록이 존재하는지 확인
4. 지문이 없으면 `issues` 에 기록
5. 지문 제시 표현이 없거나 지문이 정상적으로 있으면 `found:false`

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A18"
- `type_name`: "문장 전체 생략"
- `issues[].location`: `"stem"` (지문이 있어야 할 자리를 stem 기준으로 보고)
- `issues[].original`: 지문 참조 표현이 포함된 문제 본문 인용
- `issues[].suspected`: 지문이 필요한 문항이지만 지문이 없음을 한 문장
- `issues[].suggested`: `null`
- `confidence`: 지문 참조 표현이 명확하고 지문이 없으면 `"high"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 문장이 설명하는 보안 솔루션은 무엇인가?

① 방화벽
② 침입탐지시스템(IDS)
③ VPN
④ 허니팟
```

출력:
```json
{"question_number":99,"type_code":"A18","type_name":"문장 전체 생략","found":true,"issues":[{"location":"stem","original":"다음 문장이 설명하는 보안 솔루션은 무엇인가?","suspected":"'다음 문장이 설명하는'이라고 지문 제시를 시사하지만 문항에 지문 블록이 전혀 존재하지 않음","suggested":null}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
