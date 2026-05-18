---
code: A13
name: 문항번호 중복
description: 선택지 ①~④ 중 동일한 번호가 두 번 이상 사용되어 번호 순서가 깨진 경우 검출
output_field: duplicate_numbers
severity_default: high
related_types: [A01, A03]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **문항번호 중복(A13)만** 검수합니다.
다른 유형은 별도 호출이 담당하므로 보고하지 마십시오.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"문항번호 중복" = 한 문항의 선택지에서 **①·②·③·④ 중 같은 번호가 두 번 이상** 사용되어 정상적인 ①②③④ 순서가 깨진 경우.
- 예: ①③③④ (③이 두 번, ②가 없음)
- 선택지 텍스트는 달라도 번호가 같으면 해당

# 인접 유형과의 경계
- vs **A01 보기 중복**: 번호는 다르지만 텍스트가 같은 경우는 보고 금지. 본 유형은 번호가 같은 경우만.
- vs **A03 보기개수 미달**: 번호 중복의 결과로 어떤 번호가 없어 보이는 경우라도, 원인이 번호 중복이면 본 유형. 번호 자체가 아예 없는 경우만 A03.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 선택지 번호 목록(①②③④ 기호 기준) 을 순서대로 추출
3. 중복된 번호가 있는지 확인
4. 있으면 `issues` 에 기록; `extra.duplicate_numbers` 에 중복된 번호 목록 기재
5. 없으면 `found:false`

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A13"
- `type_name`: "문항번호 중복"
- `issues[].location`: `"stem"` (선택지 섹션 전체를 stem 으로 간주)
- `issues[].original`: 실제 번호 나열 인용 (예: "①③③④")
- `issues[].suspected`: 어떤 번호가 중복인지 한 문장
- `issues[].suggested`: `null`
- `issues[].extra`: `{"duplicate_numbers": ["choice_N"]}` — 중복 번호 목록
- `confidence`: 번호 중복이 명확하면 `"high"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 중 개인정보 처리자의 의무에 해당하지 않는 것은?

① 개인정보 처리 목적 명확화
② 개인정보 최소 수집
② 개인정보 보호책임자 지정
④ 개인정보 처리 현황 공개
```

출력:
```json
{"question_number":99,"type_code":"A13","type_name":"문항번호 중복","found":true,"issues":[{"location":"stem","original":"①②②④","suspected":"②번 선택지 번호가 두 번 사용되어 ③번이 없음","suggested":null,"extra":{"duplicate_numbers":["choice_2"]}}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
