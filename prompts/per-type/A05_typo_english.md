---
code: A05
name: 오자(영어)
description: 영문 알파벳 단어·약어에서 철자가 잘못 변형된 영어 오자 검출
output_field: typo_english
severity_default: medium
related_types: [A02, A16]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **영어 오자(A05)만** 검수합니다.
한글 오자(A02)·탈자(A16) 등 다른 유형은 별도 호출이 담당하므로 보고하지 마십시오.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"영어 오자" = 영문 단어 또는 약어에서 **알파벳 철자가 변형**되어 의도한 단어와 다른 문자열이 된 경우.
- 대소문자 오류도 포함 (예: `ssl` → 올바른 표기 `SSL`)
- 전치·대체·추가 등 한 글자 이상 알파벳이 달라진 경우

# 인접 유형과의 경계
- vs **A02 오자**: 한글 음절 자모 변형은 보고 금지. 본 유형은 영문자만.
- vs **A16 탈자**: 영문 알파벳이 **빠진** 경우는 보고 금지. 본 유형은 알파벳이 **바뀐** 경우만.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 문제 본문(stem) → 지문/인용(passage) → 선택지 ①~④(choice_1~4) 순으로 영문자 포함 단어·약어 검토
3. 철자 오류가 있는 단어·약어를 `issues` 에 기록
4. 확인할 수 없는 비표준 약어는 보고 금지

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A05"
- `type_name`: "오자(영어)"
- `issues[].location`: 결함 위치
- `issues[].original`: 오자 영문이 포함된 최소 인용
- `issues[].suspected`: 어떤 알파벳이 잘못됐는지 한 문장
- `issues[].suggested`: 올바른 영문 표기
- `confidence`: 표준 약어·단어로 오류가 명확하면 `"high"`, 비표준 약어라 불확실하면 `"medium"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 중 네트워크 보안 프로토콜에 대한 설명으로 옳지 않은 것은?

① SSL/TSL은 전송 계층에서 데이터를 암호화한다.
② IPSec은 네트워크 계층에서 동작한다.
③ SSH는 원격 접속 시 데이터를 암호화한다.
④ HTTPS는 HTTP에 SSL/TLS를 적용한 것이다.
```

출력:
```json
{"question_number":99,"type_code":"A05","type_name":"오자(영어)","found":true,"issues":[{"location":"choice_1","original":"SSL/TSL","suspected":"'TSL'은 'TLS'의 알파벳 전치 오자(L과 S 순서 뒤바뀜)","suggested":"SSL/TLS"}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
