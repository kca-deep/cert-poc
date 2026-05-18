---
code: A17
name: 지문 원문자 탈자
description: 지문(passage) 내 괄호 안에 들어가야 할 원문자(㉠·㉡·㉢·㉣ 또는 ①~④)가 빠진 경우 검출
output_field: marker_dropout
severity_default: medium
related_types: [A16, A19]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **지문 원문자 탈자(A17)만** 검수합니다.
일반 글자 탈자(A16)·기타 특수기호 누락(A19) 등은 별도 호출이 담당합니다.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"지문 원문자 탈자" = 지문(passage) 의 괄호 안에 넣어야 할 **원문자(㉠·㉡·㉢·㉣ 등 한글 원 숫자)**가 빠져 괄호가 비어 있는 경우.
- 예: `( ㉡ )` 이어야 할 곳이 `( )` 로 되어 있는 경우
- 지문 내 열거 구조에서 특정 기호만 누락된 경우

# 인접 유형과의 경계
- vs **A16 탈자**: 일반 한글 음절·영문자가 빠진 경우는 보고 금지. 본 유형은 ㉠㉡ 등 원문자만.
- vs **A19 특수기호 누락**: 「」·±·· 등 기타 특수기호 누락은 보고 금지.
- vs **A14 정답유출**: 괄호 안에 이미 내용이 채워진 경우는 보고 금지. 본 유형은 채워져야 할 원문자가 비어 있는 경우.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 지문(passage) 블록에서 `( )` 형태의 괄호를 모두 찾기
3. 괄호 안에 원문자(㉠㉡㉢㉣ 등)가 있어야 하는 문맥인지 확인
4. 원문자가 빠진 괄호가 있으면 `issues` 에 기록; `extra.missing_marker` 에 예상 원문자 기재
5. 없으면 `found:false`

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A17"
- `type_name`: "지문 원문자 탈자"
- `issues[].location`: `"passage"`
- `issues[].original`: 원문자가 빠진 괄호를 포함한 짧은 인용
- `issues[].suspected`: 어떤 원문자가 빠진 괄호인지 한 문장
- `issues[].suggested`: 원문자를 채운 올바른 형태 (확신이 없으면 `null`)
- `issues[].extra`: `{"missing_marker": "㉠"}` 등 예상 원문자 (추정 가능하면 기재)
- `confidence`: 문맥상 원문자가 명확하면 `"high"`, 어떤 원문자인지 불확실하면 `"medium"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 괄호에 들어갈 적합한 용어를 바르게 묶은 것은?

(지문) ( )은 비밀키 방식으로, ( ㉡ )은 공개키 방식으로 동작한다.

① ㉠ 대칭키 암호화  ㉡ 비대칭키 암호화
② ㉠ 해시함수  ㉡ 대칭키 암호화
③ ㉠ 비대칭키 암호화  ㉡ 대칭키 암호화
④ ㉠ 해시함수  ㉡ 비대칭키 암호화
```

출력:
```json
{"question_number":99,"type_code":"A17","type_name":"지문 원문자 탈자","found":true,"issues":[{"location":"passage","original":"( )은 비밀키 방식으로","suspected":"첫 번째 괄호 안에 원문자 '㉠'이 빠진 것으로 보임 — 두 번째 괄호에 '㉡'이 있는 것과 대조됨","suggested":"( ㉠ )은 비밀키 방식으로","extra":{"missing_marker":"㉠"}}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
