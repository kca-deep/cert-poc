---
code: A01
name: 보기 중복
description: 보기 ①~④ 사이에 동일한 텍스트가 둘 이상 존재하는지 검출
output_field: duplicate_pair
severity_default: high
related_types: []
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지에서 **보기 사이의 중복(A01)만** 검수합니다.
다른 유형은 별도 호출이 담당하므로 본 호출에서는 보고하지 마십시오.
공통 규약은 `_shared/system_preamble.md` 를 따릅니다.

# 정의
"보기 중복" = 한 문항의 선택지 ①·②·③·④ 중 **둘 이상의 선택지가 표면적으로 같은 텍스트** 인 경우.

판단 기준은 표면적 일치만 사용합니다.
- 앞뒤 공백·구두점 차이는 무시하되, **글자(자모)는 그대로 일치** 해야 동일로 봅니다.
- 항목 나열형 선택지(여러 개의 항목/매핑을 한 줄에 적은 형태)는 **항목 순서·매핑이 모두 같을 때만** 동일로 봅니다.
- 의미는 같지만 표현이 다른 경우는 중복이 아닙니다 (동의어·요약·재배열 모두 보고 금지).

# 인접 유형과의 경계
- 본 유형은 선택지 간 표면 비교이므로 다른 유형과 영역이 겹치지 않습니다.
- 한 선택지 내부의 오자·맞춤법·띄어쓰기 결함은 보고하지 마십시오.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 선택지 ①·②·③·④ 의 텍스트를 각각 추출하고 앞뒤 공백·구두점만 정규화
3. C(4,2)=6 쌍을 비교해 위 정의에 해당하는 쌍을 식별
4. 동일 쌍이 있으면 `issues` 에 1건씩 기록 — 번호가 더 큰 선택지를 `location`, 더 작은 쪽을 `extra.duplicate_with` 에 넣습니다
5. 없으면 `found:false`, `issues:[]`

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A01"
- `type_name`: "보기 중복"
- `issues[].location`: 동일 쌍 중 번호가 더 큰 선택지 (`choice_2`/`choice_3`/`choice_4`)
- `issues[].original`: 그 선택지의 짧은 인용
- `issues[].suspected`: 어느 선택지와 동일한지 한 문장
- `issues[].suggested`: 어떻게 고쳐야 할지 단서가 없으면 `null`
- `issues[].extra`: `{"duplicate_with": "choice_X"}` 로 짝 명시
- `confidence`: 완전 일치 `"high"`, 항목 매핑 일치 `"medium"`

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

입력:
```
## 99.
다음 중 대칭키 암호 알고리즘만으로 묶인 것은?

① AES, DES, SEED
② AES, DES, SEED
③ RSA, ECC, ElGamal
④ AES, RSA, SHA-256
```

출력:
```json
{"question_number":99,"type_code":"A01","type_name":"보기 중복","found":true,"issues":[{"location":"choice_2","original":"AES, DES, SEED","suspected":"①번 선택지와 텍스트가 완전 동일","suggested":null,"extra":{"duplicate_with":"choice_1"}}],"confidence":"high"}
```

# 입력 문항
{{QUESTION_BLOCK}}
