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
2. **선택지 구역에서만** 번호 추출 — 문항 끝 독립 줄로 시작하는 ①②③④ 영역. 지문·본문·표 안의 ①②③④는 선택지 번호가 아니므로 제외
3. 추출한 선택지 번호 목록에서 중복 번호 확인
4. 정확히 ①②③④ 순서로 각 1회이면 **즉시 `found:false`** 출력 후 종료
5. 중복 번호가 있으면 `issues` 에 기록

# 출력
`_shared/output_schema.json` 을 따르는 JSON 객체 1개만 출력. 코드펜스·설명 금지.

- `type_code`: "A13"
- `type_name`: "문항번호 중복"
- `issues[].location`: `"stem"` (선택지 섹션 전체를 stem 으로 간주)
- `issues[].original`: 실제 번호 나열 인용 (예: "①③③④")
- `issues[].suspected`: 어떤 번호가 중복인지 한 문장 (예: "②번 중복, ③번 없음")
- `issues[].suggested`: `null`
- `confidence`: 번호 중복이 명확하면 `"high"`
- **`extra` 필드 출력 금지** — 응답 길이 절약을 위해 생략

# Few-shot (합성 예시 — 실제 시험에 등장하지 않는 가공 문항)

## 예시 1 — 번호 중복 발견 (found:true)

입력:
```
## 99.
다음 중 접근통제의 원칙에 해당하지 않는 것은?

① 최소 권한의 원칙
② 직무 분리의 원칙
③ 알 필요성의 원칙
③ 감사 추적의 원칙
```

출력:
```json
{"question_number":99,"type_code":"A13","type_name":"문항번호 중복","found":true,"issues":[{"location":"stem","original":"①②③③","suspected":"③번 중복, ④번 없음","suggested":null}],"confidence":"high"}
```

## 예시 2 — 정상 (found:false)

입력:
```
## 98.
다음 중 해시 함수의 특성으로 옳지 않은 것은?

① 같은 입력에는 항상 같은 출력이 나온다.
② 출력 길이는 입력 길이에 관계없이 일정하다.
③ 역방향 계산(복호화)이 쉽다.
④ 입력이 조금만 달라도 출력이 크게 달라진다.
```

출력:
```json
{"question_number":98,"type_code":"A13","type_name":"문항번호 중복","found":false,"issues":[],"confidence":"high"}
```

# [간결 응답 지시]
이 검수는 선택지 번호 목록 추출만으로 결론을 낼 수 있습니다.
추론을 최소화하고 즉시 JSON을 출력하십시오.
`issues[].original` 은 번호 기호만 (예: "①②③③") 15자 이하로 작성하십시오.

# 입력 문항
{{QUESTION_BLOCK}}
