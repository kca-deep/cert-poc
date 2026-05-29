---
group_code: G1
group_name: 글자·표기 오류
types: [A02, A04, A05, A06, A16]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **글자·표기 오류 5가지 유형**을 한 번에 검수합니다.
공통 규약은 `_shared/system_preamble.md`를 따릅니다.

# 유형 정의

| 코드 | 유형 | 판별 기준 |
|------|------|---------|
| A02 | 오자 | 자모(초성·중성·종성) 변형 → 표준국어대사전 미등재 단어 | 수립→수랍, 외부→외뷰 |
| A04 | 맞춤법 | 표준어이나 어미·표기 규범 위반 | 않→안, 됬→됐, 안게→않게 |
| A05 | 영어 오자 | 영문 알파벳 변형 | DoS→DoZ, DRM→DPM |
| A06 | 띄어쓰기 | 어절 간 공백 추가·누락 | 마이데이터→마 이 데 이 터 |
| A16 | 탈자 | 한글·영문 글자 자체 탈락 | 합니다→함니다(ㅂ탈락), 합니다→함다(ㅂ+니 탈락) |

# 유형 간 경계 (중요)

- **A02 vs A04**: 결과 단어가 표준국어대사전 미등재 → A02. 사전에 있으나 규범 위반 → A04.
- **A02 vs A16**: 글자가 **바뀐** 경우 A02, 글자가 **빠진** 경우 A16. **복합(바뀜+빠짐) 시 A02·A16 동시 보고 가능.**
  - 예) `합니다→함다`: `ㅂ→ㅁ` 변형(A02) + `니` 탈락(A16) 동시 발생
- **A06 경계**: 단글자들이 공백으로 분리된 패턴(예: `마 이 데 이 터`, `저 권`)은 A06이며 A02 아님.
- **A04 vs A02**: `안게`(안→않, 맞춤법) vs `외뷰`(외부 자모 변형, 사전 미등재) — 사전 존재 여부로 구분.

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. 문제 본문(stem) → 지문(passage) → 선택지 ①~④ 순으로 **어절 하나씩** 검토
3. 각 어절에 대해 순서대로:
   - **Step A (사전 확인)**: 표준국어대사전에 없는 단어? → A02 후보, Step B 진행
   - **Step B (자모 확인)**: 어떤 자모가 바뀌었나? 동시에 글자가 빠졌나? → A02·A16 판별
   - **Step C (맞춤법)**: 사전에 있으나 어미·표기 규범 위반? → A04
   - **Step D (영어)**: 영문 알파벳 변형? → A05
   - **Step E (공백)**: 어절 간 공백 추가·누락? → A06
4. **탐지 적극성**: 비표준어·규범 위반이 명백하면 반드시 보고. 신조어·IT 용어일 가능성이 있어도 시험지는 표준어만 사용하므로 found:true로 보고.
5. `found:false`는 모든 어절이 Step A~E를 통과한 경우에만.

# 출력
코드펜스·설명 없이 JSON 1개만 출력.

```
{
  "question_number": N,
  "group_code": "G1",
  "group_name": "글자·표기 오류",
  "results": [
    {"type_code": "A02", "type_name": "오자", "found": true/false, "issues": [{"location": "...", "original": "...", "suspected": "...", "suggested": "..."}], "confidence": "high|medium"},
    {"type_code": "A04", "type_name": "맞춤법", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A05", "type_name": "오자(영어)", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A06", "type_name": "띄어쓰기", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A16", "type_name": "탈자", "found": false, "issues": [], "confidence": "high"}
  ]
}
```

**반드시 5개 유형 모두 results[]에 포함할 것.**

# Few-shot

입력:
```
## 2.
정보자산 폐기 절차에 대한 설명으로 틀린 것은?

① 외뷰 업체에 위탁하여 처리하여서는 안된다.
② 복구 또는 재생되지 않도록 하여야 한다.
③ 폐기일자, 담당자 등의 내용을 담은 폐기이력을 보관하여야 한다.
④ 폐기 방법, 폐기 관리대장 기록 등의 사항을 포함하여 수립하여야 한다.
```

Step A: `외뷰` → 표준국어대사전 미등재 → Step B: `외부(ㅜ)→외뷰(ㅠ+ㅜ)` 중성 변형 → A02

출력:
{"question_number":2,"group_code":"G1","group_name":"글자·표기 오류","results":[{"type_code":"A02","type_name":"오자","found":true,"issues":[{"location":"choice_1","original":"외뷰 업체에","suspected":"'외뷰'는 '외부'의 자모 오자(중성 ㅜ→ㅠ+ㅜ)","suggested":"외부 업체에"}],"confidence":"high"},{"type_code":"A04","type_name":"맞춤법","found":false,"issues":[],"confidence":"high"},{"type_code":"A05","type_name":"오자(영어)","found":false,"issues":[],"confidence":"high"},{"type_code":"A06","type_name":"띄어쓰기","found":false,"issues":[],"confidence":"high"},{"type_code":"A16","type_name":"탈자","found":false,"issues":[],"confidence":"high"}]}

# 입력 문항
{{QUESTION_BLOCK}}
