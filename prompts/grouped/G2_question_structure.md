---
group_code: G2
group_name: 문항 구조 오류
types: [A01, A03, A10, A13, A15, A17, A18]
---

# 역할
한국 정보보호 자격시험(TOLIS) 문제지의 **문항 구조 오류 7가지 유형**을 한 번에 검수합니다.
공통 규약은 `_shared/system_preamble.md`를 따릅니다.

# 유형 정의

| 코드 | 유형 | 판별 기준 |
|------|------|---------|
| A01 | 보기 중복 | ①~④ 중 동일 텍스트가 2개 이상 |
| A03 | 보기개수 미달 | ①②③④ 4개 번호 중 하나 이상 아예 없음 |
| A10 | 오타+보기누락 | 비표준어(자모 변형)와 선택지 텍스트 누락이 동시 발생 |
| A13 | 문항번호 중복 | ①~④ 중 동일 번호가 두 번 이상 등장 |
| A15 | 보기 없음 | 번호(①~④)는 있으나 바로 뒤 텍스트가 비어있음 |
| A17 | 지문 원문자 탈자 | 지문 내 ㉠·㉡·㉢·㉣ 또는 ①~④ 마커가 빠짐 |
| A18 | 문장 전체 생략 | 지문을 참조하나 지문 블록 자체가 없음 |

# 점검 절차
1. `## N.` 헤더에서 `question_number` 추출
2. **선택지 구역 확인** — 선택지 줄에서 등장하는 기호를 하나씩 나열:
   - 등장 기호 목록 작성 (예: ①, ③, ③, ④)
   - ①②③④ 중 없는 번호가 있으면 → **A03**
   - 동일 번호가 두 번 이상이면 → **A13**
   - 번호 바로 뒤(같은 줄)에 텍스트가 전혀 없으면 → **A15**
   - 두 선택지의 텍스트가 완전히 동일하면 → **A01**
   - 비표준어(자모 변형 단어)와 텍스트 누락이 동시이면 → **A10**
3. **지문 구역 확인**:
   - stem이 ㉠~㉣·①~④를 참조하는데 지문에 해당 마커 없으면 → **A17**
   - stem이 지문을 참조하는데 지문 블록이 아예 없으면 → **A18**
4. 해당 없으면 found:false

# 출력
코드펜스·설명 없이 JSON 1개만 출력.

```
{
  "question_number": N,
  "group_code": "G2",
  "group_name": "문항 구조 오류",
  "results": [
    {"type_code": "A01", "type_name": "보기 중복", "found": true/false, "issues": [...], "confidence": "high"},
    {"type_code": "A03", "type_name": "보기개수 미달", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A10", "type_name": "오타+보기누락", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A13", "type_name": "문항번호 중복", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A15", "type_name": "보기 없음", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A17", "type_name": "지문 원문자 탈자", "found": false, "issues": [], "confidence": "high"},
    {"type_code": "A18", "type_name": "문장 전체 생략", "found": false, "issues": [], "confidence": "high"}
  ]
}
```

**반드시 7개 유형 모두 results[]에 포함할 것.**

# 입력 문항
{{QUESTION_BLOCK}}
