# 웹앱 프론트엔드 구현 계획 (frontend-first)

> 상위 문서: [webapp_plan.md](./webapp_plan.md) · 디자인: [DESIGN.md](./DESIGN.md)
> 이 문서는 **프론트엔드 우선** 구현의 결정사항·아키텍처·구현 순서를 담는다.

---

## 0. 확정된 설계 결정

| 항목 | 결정 |
|------|------|
| 진행 UX | **백그라운드 비동기 + 재방문 가능**. SSE 끊겨도 재접속 시 현재 상태 복원. 다중 세션 동시 분석 가능 |
| 진행 표시 밀도 | **레이어 진행바 + 문항 도트** (계획서 6.2 수준) |
| 데이터 전략 | **목업 fixture + 시뮬레이션 SSE로 프론트 먼저**. 모든 서버 I/O는 `lib/api.ts`에 격리 → 추후 FastAPI 교체. `NEXT_PUBLIC_USE_MOCK` 플래그 |
| 앱 셸 | **좌측 고정 사이드바**(~200px) + 우측 메인 |
| 라우트 단순화 | 계획서의 `/review` 별도 라우트 제거 → 리뷰 액션을 대시보드 카드에 인라인 흡수 |
| 폰트 | Geist → **Inter**(Supabase Circular 대체, display weight 500). shadcn 폰트 순환참조 버그 수정 |

---

## 1. 기술 스택 (설치 완료)

- Next.js **16.2.6** (App Router, Turbopack), React 19.2.4, TypeScript 5
- Tailwind **v4** + shadcn/ui (radix base)
- shadcn 컴포넌트: button card badge table sheet dialog progress separator tabs scroll-area input textarea label **sonner**(toast 대체) tooltip skeleton
- 상태: @tanstack/react-query(서버 상태) · zustand(클라 상태)
- 기타: react-dropzone, react-markdown+remark-gfm, date-fns, lucide-react, cva, clsx, tailwind-merge

> **Next.js 16 주의**: `params`는 Promise(await 필요). `PageProps<'/route'>` 전역 헬퍼 타입 사용. 새 코드 작성 전 `node_modules/next/dist/docs/` 확인(AGENTS.md).

---

## 2. 유형 카탈로그 (A01~A21) · 레이어 매핑

| 코드 | 한글명 | 레이어 | 그룹 |
|------|--------|--------|------|
| A01 | 보기 중복 | L0 코드 | — |
| A02 | 오자 | L2 | — |
| A03 | 보기개수 미달 | L0 코드 | — |
| A04 | 맞춤법 오류 | L1 | G1 |
| A05 | 영문 오타 | L1 | G1 |
| A06 | 띄어쓰기 오류 | L1 | G1 |
| A07 | 특수기호 누락 | L2 | — |
| A08 | 매끄럽지 못한 문장 | L2 | — |
| A09 | 법령명 오류 | L1 | G4 |
| A10 | 오타·보기 누락 | L2 | — |
| A11 | 낙서형 1 | L1 | G5 |
| A12 | 낙서형 2 | L2 | — |
| A13 | 문항번호 중복 | L0 코드 | — |
| A14 | 정답 노출 | L1 | G5 |
| A15 | 보기 없음 | L0 코드 | — |
| A16 | 탈자 | L2 | — |
| A17 | 지문 원문자 탈자 | L0 코드 | — |
| A18 | 문장 전체 생략 | L0 코드 | — |
| A19 | 특수기호 누락(지문) | L2 | — |
| A20 | 법조항 오류 | L1 | G4 |
| A21 | 잘못된 단어 | L2 | — |

- 레이어 배지 색: **L0 = canvas-night(dark)**, **L1 = violet #644fc1**, **L2 = indigo #054cff**

---

## 3. 데이터 모델 (`lib/types.ts`)

파이프라인 출력 스키마(`prompts/_shared/output_schema.json`) 및 DB 스키마(webapp_plan §4) 기반.

```ts
type SessionStatus = "uploading" | "parsing" | "running" | "done" | "error";
type Layer = 0 | 1 | 2;
type Confidence = "low" | "medium" | "high";
type IssueLocation = "stem" | "passage" | "choice_1" | "choice_2" | "choice_3" | "choice_4";
type ReviewActionType = "confirmed" | "rejected" | "pending";

interface Session { id; createdAt; originalFilename; fileType: "hwp"|"hwpx"|"pdf";
  status: SessionStatus; questionCount; foundCount; elapsedSeconds? }
interface Question { qNumber; mdText }
interface Issue { location: IssueLocation; original; suspected; suggested?: string|null; extra?: object }
interface AnomalyResult { qNumber; typeCode; layer: Layer; found; confidence?: Confidence;
  issues: Issue[]; filtered?: boolean; filterReason?: string }
interface ReviewAction { qNumber; typeCode; reviewer; action: ReviewActionType; comment }
type ProgressEvent =  // SSE 유니온 (webapp_plan §5)
  | { event:"layer_start"; layer:Layer; totalQ?:number }
  | { event:"q_layer0_done"; q:number; types:Record<string,boolean> }
  | { event:"q_type_done"; layer:Layer; q:number; typeCode:string; found:boolean; confidence?:Confidence }
  | { event:"layer_done"; layer:Layer; found:number }
  | { event:"postprocess"; filtered:number }
  | { event:"done"; totalFound:number; elapsed:number }
  | { event:"error"; message:string };
```

---

## 4. 디렉토리 구조 (web/)

```
app/
  layout.tsx              # 루트: Inter 폰트 + Providers + AppShell(사이드바)
  providers.tsx           # QueryClientProvider + TooltipProvider + Toaster (client)
  globals.css             # Supabase 토큰 → shadcn 변수 매핑 + 앱 토큰
  page.tsx                # → redirect /sessions
  upload/page.tsx         # (다음 단계) 드롭존
  sessions/
    page.tsx              # 히스토리 목록
    [id]/page.tsx         # 서버: await params → <SessionView id>
components/
  layout/Sidebar.tsx
  dashboard/
    SessionView.tsx       # client 오케스트레이터 (status 분기: running→진행 / done→대시보드)
    SessionHeader.tsx     # 파일명 + 탐지건수 + Excel 버튼(stub)
    QuestionList.tsx      # 좌 문항 목록 + 필터
    QuestionDetail.tsx    # 우 원문 + 탐지카드
    AnomalyCard.tsx       # 탐지 카드 + 리뷰 액션(인라인)
    MatrixView.tsx        # 문항×유형 매트릭스 탭
  progress/PipelineProgress.tsx   # (다음 단계) 레이어바 + 문항 도트
lib/
  types.ts  constants.ts  api.ts  sse.ts  utils.ts
  mock/fixtures.ts        # 세션 3종(완료/정상/진행중) + 문항 + 탐지결과
  stores/review.ts        # zustand 리뷰 상태
```

---

## 5. 구현 순서

1. **공통 레이아웃** — globals.css 토큰·Inter, providers, Sidebar, 루트 layout, `/` 리다이렉트  ← 이번
2. **lib 기반** — types, constants, mock fixtures, api, review store  ← 이번
3. **대시보드** — SessionView/Header/QuestionList/QuestionDetail/AnomalyCard/MatrixView  ← 이번
4. 히스토리 목록 `/sessions` (네비 연결용 최소 구현)  ← 이번
5. 업로드 `/upload` + FileDropzone  ← 다음
6. 진행 화면 PipelineProgress + mock SSE(`lib/sse.ts`)  ← 다음
7. Excel/PDF 내보내기 — 백엔드 연결 후 활성화(현재 stub 버튼)
8. FastAPI 연결 — `lib/api.ts`·`lib/sse.ts` 실서버 교체

---

## 6. 컴팩트 디자인 적용 (DESIGN.md 기반)

- 에메랄드는 화면당 filled 1개("+ 새 분석" CTA). 나머지 outline/ghost
- 카드 padding 12px, 버튼 4px 10px, body 13px, radius 6px
- 탐지 카드 상태: 확인→에메랄드 left-border 4px / 반려→tomato / 보류→violet
- 매트릭스: 흰 배경 + 채워진 에메랄드 도트(found), filtered=yellow, error=tomato
- 색은 상태만 표현(탐지=에메랄드, 에러=tomato, 보류=violet) — 장식용 색 없음
