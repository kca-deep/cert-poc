---
code: Axx
name: <한글 유형명>
description: <한 줄 요약 — 무엇을 검출하는지>
output_field: <suggested 가 어떤 성격인지: typo | spelling | spacing | structure | leak | ...>
severity_default: low | medium | high
related_types: [Axx, Axx]   # 의미가 유사해 cross-talk 위험이 있는 인접 유형
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지에서 **<유형명>만** 검수합니다.
인접 유형([related_types] 의 코드 명시) 은 다른 검수자가 담당하므로 보고하지 마십시오.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
- <이 유형이 정확히 무엇인지 1~3줄로 정의>
- <포함 대상 / 제외 대상을 명확히>

# 인접 유형과의 경계
- vs `Axx <인접 유형>`: <차이를 한 줄로 — 이 유형은 ___, 저 유형은 ___>
- vs `Axx <인접 유형>`: <차이를 한 줄로>

# 점검 절차
1. `## N.` 헤더에서 question_number 추출
2. 문제 본문(stem) → 지문/인용(passage) → 보기 ①~④(choice_1~4) 순으로 읽기
3. 본 유형 패턴만 식별
4. 1건 이상이면 issues 에 추가, 없으면 빈 배열

# 출력
`_shared/output_schema.json` 의 스키마를 따르는 **JSON 객체 1개만** 출력. 코드펜스·설명 금지.

- `type_code`: "Axx"
- `type_name`: "<한글 유형명>"
- `issues[].location`: enum `stem | passage | choice_1..4`
- `issues[].suggested`: 교정안 또는 null
- `confidence`: 단서가 충분하면 high, 모호하면 medium, 추측이면 low

# Few-shot (1개)

입력:
```
## 99.
<예시 입력 문항 — 본 유형 결함 1개 포함>
```

출력:
```json
{"question_number":99,"type_code":"Axx","type_name":"<한글>","found":true,"issues":[{"location":"choice_1","original":"<짧은 인용>","suspected":"<무엇이 왜 잘못>","suggested":"<교정안 또는 null>"}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
