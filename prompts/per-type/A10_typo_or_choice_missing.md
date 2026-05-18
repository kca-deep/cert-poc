---
code: A10
name: 오타+보기누락
description: 문제 본문·선택지에서 오자(자모 변형)와 선택지 텍스트 누락이 함께 또는 개별로 발생한 경우 검출
output_field: typo_or_missing
severity_default: high
related_types: [A02, A15]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **오타+보기누락(A10)만** 검수합니다.
다른 유형은 별도 호출이 담당하므로 보고하지 마십시오.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"오타+보기누락" = 같은 문항에서 다음 중 하나 이상이 발생한 경우:
1. **오타**: 문제 본문·지문·선택지에서 한글 자모 변형으로 의도한 단어와 다른 글자가 된 경우 (A02 오자와 동일 기준)
2. **보기 텍스트 누락**: 선택지 번호(①②③④) 는 있으나 그 뒤 텍스트가 비어 있거나 심각하게 잘려 있는 경우 (A15 보기 없음과 동일 기준)

두 조건이 동시에 발생한 경우 각각 별도 issue 로 기록합니다.

# 인접 유형과의 경계
- vs **A02 오자**: 오타 단독 발생은 A02 가 담당. 본 유형은 보기 누락과 함께 또는 이 호출이 담당하는 문항.
- vs **A15 보기 없음**: 보기 누락 단독 발생은 A15 가 담당.
- vs **A16 탈자**: 글자가 아예 빠진 경우는 보고 금지. 본 오타는 글자가 바뀐 경우.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 문제 본문(stem) → 지문(passage) → 선택지 ①~④ 순으로 검토
3. 오자(자모 변형으로 다른 음절이 된 단어) 가 있으면 issue 로 기록
4. 번호가 있는 선택지 중 텍스트가 비어 있거나 잘린 선택지가 있으면 issue 로 기록
5. 아무 조건도 해당 없으면 `found:false`

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A10"
- `type_name`: "오타+보기누락"
- `issues[].location`: 오타면 해당 위치, 보기 누락이면 `"choice_N"`
- `issues[].original`: 오타 단어 또는 빈 선택지 번호 인용
- `issues[].suspected`: 오타이면 "'X'는 'Y'의 자모 오자", 누락이면 "②번 선택지 텍스트가 없음" 형태 한 문장
- `issues[].suggested`: 오타 교정 후보 또는 `null`
- `confidence`: 오자·누락이 명확하면 `"high"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 중 악성코드 유형에 대한 설명으로 틀린 것은?

(지문) 악성코드는 사용자의 동의 없이 컴퓨터에 설치되어 피래를 주는 소프트웨어이다.

①
② 웜은 네트워크를 통해 자동으로 전파된다.
③ 트로이목마는 정상 프로그램으로 위장하여 동작한다.
④ 스파이웨어는 사용자 정보를 몰래 수집한다.
```

출력:
```json
{"question_number":99,"type_code":"A10","type_name":"오타+보기누락","found":true,"issues":[{"location":"passage","original":"피래를 주는","suspected":"'피래'는 '피해'의 자모 오자(ㅐ→ㅐ 아닌 ㅐ, 실제 ㅐ→ㄹ 교체)","suggested":"피해를 주는"},{"location":"choice_1","original":"①","suspected":"①번 선택지 텍스트가 없음","suggested":null}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
