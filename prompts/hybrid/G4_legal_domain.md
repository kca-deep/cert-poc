---
group_code: G4
group_name: 법령·도메인 오류
layer: 1
types: [A09, A20]
excluded: [A19]
note: A19(법령 특수기호 누락)는 100% 미탐으로 per-type 처리
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **법령 오류 2가지 유형**을 검수합니다.
공통 규약은 `_shared/system_preamble.md`를 따릅니다.

> **범위 주의**: 법령 특수기호(「」) 누락(A19)은 이 그룹에서 다루지 않습니다.
> 법령명 오류(A09)와 조항 번호 오류(A20)만 검수합니다.

# 유형 정의

| 코드 | 유형 | 판별 기준 |
|------|------|---------|
| A09 | 틀린 법령명 | 등장하는 법령의 정식 명칭이 실제와 다름 |
| A20 | 틀린 법령 조항 | 인용된 법령의 조·항·호 번호가 실제와 다름 |

# 주요 정보보호 법령 정식 명칭

| 올바른 명칭 | 자주 나오는 오류 표기 |
|------------|-------------------|
| 정보통신망 이용촉진 및 정보보호 등에 관한 법률 | 정보통신망 **사용**촉진 및 … / 정보통신망 이용 **촉진** 및 … |
| 개인정보 보호법 | 개인**정보보호**법 (띄어쓰기 오류는 A06) |
| 정보보호산업의 진흥에 관한 법률 | — |
| 정보통신기반 보호법 | — |
| 특정 금융거래정보의 보고 및 이용 등에 관한 법률 | — |
| 전자서명법 | — |
| 신용정보의 이용 및 보호에 관한 법률 | — |

# 점검 절차

1. `## N.` 헤더에서 `question_number` 추출
2. 문제 본문·지문·선택지에서 법령명 추출
3. **A09**: 추출된 법령명이 위 정식 명칭과 한 글자라도 다른가?
   - 오류 확인 시 found:true, `confidence:"high"`
   - 법령명이 없거나 판단 불가이면 found:false
4. **A20**: `제N조`, `제N항`, `제N호` 형태의 조항 번호가 명백히 실제 법령과 다른가?
   - 불확실하면 반드시 found:false (`confidence:"high"`)
   - 명백한 오류만 보고

# 출력
코드펜스·설명 없이 JSON 1개만 출력.

```
{
  "question_number": N,
  "group_code": "G4",
  "group_name": "법령·도메인 오류",
  "results": [
    {"type_code": "A09", "type_name": "틀린 법령명", "found": true/false, "issues": [{"location": "stem|passage|choice_1~4", "original": "오류 법령명", "suspected": "설명", "suggested": "정식 법령명"}], "confidence": "high|medium"},
    {"type_code": "A20", "type_name": "틀린 법령 조항", "found": false, "issues": [], "confidence": "high"}
  ]
}
```

**반드시 2개 유형 모두 results[]에 포함할 것.**

# Few-shot

입력:
```
## 9.
다음 중 "정보보호 공시 제도"에 관한 사항을 포함하고 있는 법령명은 무엇인가?

① 정보보호산업의 진흥에 관한 법률
② 정보통신기반 보호법
③ 정보통신망 사용촉진 및 정보보호 등에 관한 법률
④ 개인정보 보호법
```

Step A09: ③의 `정보통신망 사용촉진 및 정보보호 등에 관한 법률` → 정식 명칭은 `정보통신망 **이용촉진** 및 정보보호 등에 관한 법률` → 오류

출력:
{"question_number":9,"group_code":"G4","group_name":"법령·도메인 오류","results":[{"type_code":"A09","type_name":"틀린 법령명","found":true,"issues":[{"location":"choice_3","original":"정보통신망 사용촉진 및 정보보호 등에 관한 법률","suspected":"'사용촉진'은 '이용촉진'의 오기","suggested":"정보통신망 이용촉진 및 정보보호 등에 관한 법률"}],"confidence":"high"},{"type_code":"A20","type_name":"틀린 법령 조항","found":false,"issues":[],"confidence":"high"}]}

# 입력 문항
{{QUESTION_BLOCK}}
