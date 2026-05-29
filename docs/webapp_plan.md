# 시험지 윤문 웹앱 구현 계획

> 디자인 기준: [Supabase DESIGN.md](./DESIGN.md) (awesome-design-md) — 에메랄드 그린 + 화이트 캔버스 + 컴팩트 요소

---

## 1. 시스템 개요

```
사용자
 │
 ▼
[Next.js 웹앱 :3000]
 │ API 프록시
 ▼
[FastAPI 백엔드 :8000]  ←──→  [SQLite DB]
 │                                  │
 ├── HWP 파싱 (kordoc + Node.js)    │
 ├── 하이브리드 파이프라인 실행      │
 │     ├── Layer 0: 코드 탐지       │
 │     ├── Layer 1: 그룹 LLM        │
 │     └── Layer 2: per-type LLM    │
 └── SSE 실시간 진행률 스트리밍      │
                                     │
[로컬 LLM 서버 :8081]               │
(EXAONE-3.5-32B, llama.cpp)         │
```

---

## 2. 기술 스택

> **보안 정책**: 클라이언트에서 파일 생성 없음 (Excel/PDF 모두 서버 생성). `xlsx`(SheetJS) 제외 — CVE 다수, npm 버전 수년간 미업데이트.

### 프론트엔드 (web/)

| 패키지 | 버전 | 용도 | 비고 |
|--------|------|------|------|
| next | ^16.2.6 | App Router + Turbopack | 2026 LTS |
| react / react-dom | ^19.2.6 | UI 라이브러리 | Next.js 16 필수 |
| typescript | ^5.8.3 | 타입 시스템 | |
| tailwindcss | ^4.3.0 | 유틸리티 CSS | v4 — postcss 내장 |
| lucide-react | 최신 | 아이콘 | |
| class-variance-authority | ^0.7.1 | 컴포넌트 변형 | |
| clsx | ^2.1.1 | 클래스 조합 | |
| tailwind-merge | ^3.3.0 | 클래스 병합 | |
| react-dropzone | ^14.3.8 | 파일 드래그앤드롭 | |
| react-markdown | ^9.0.3 | 마크다운 렌더링 | |
| remark-gfm | ^4.0.1 | GFM 마크다운 플러그인 | |
| @tanstack/react-query | ^5.100.11 | 서버 상태 관리 | |
| zustand | ^5.0.4 | 클라이언트 상태 관리 | |
| date-fns | ^4.1.0 | 날짜 포맷 | |

> ❌ **제외**: `xlsx` (SheetJS) — prototype pollution, DoS CVE 다수, npm 최신본 0.18.5가 2023 이후 미업데이트  
> ❌ **제외**: 클라이언트 PDF/Excel 라이브러리 전체 — 내보내기는 FastAPI 서버에서 처리, 브라우저에서 단순 링크 클릭

**shadcn/ui (CLI v4, Rhea 스타일 — 컴팩트 제품 UI 특화):**
```bash
npx shadcn@4.8.2 init --style rhea
npx shadcn@latest add button card badge table sheet dialog progress toast separator tabs scroll-area input textarea label
```

### 백엔드 (api/)

| 패키지 | 버전 | 용도 |
|--------|------|------|
| fastapi | ^0.136.1 | API 프레임워크 (2026-04 최신) |
| uvicorn[standard] | ^0.48.0 | ASGI 서버 (2026-05 최신) |
| python-multipart | ^0.0.20 | 파일 업로드 |
| sse-starlette | ^2.3.0 | Server-Sent Events |
| aiofiles | ^24.1.0 | 비동기 파일 I/O |
| pdfplumber | ^0.11.4 | PDF → 텍스트 파싱 |
| openpyxl | ^3.1.5 | Excel 내보내기 (**서버 전용**) |

### 버전 호환성 매트릭스

| | Next.js 16 | React 19 | Tailwind 4 | shadcn Rhea |
|---|---|---|---|---|
| 호환 | ✅ | ✅ (필수) | ✅ | ✅ |

### 보안 검토 결과

| 라이브러리 | 상태 | 결정 |
|-----------|------|------|
| xlsx (SheetJS) | ❌ prototype pollution, DoS CVE | **제거** |
| exceljs | ⚠️ 3년 이상 업데이트 없음 | **미사용** (서버 openpyxl 대체) |
| @react-pdf/renderer | ✅ 취약점 없음 | SSR 사용 가능 (선택적) |
| react-dropzone | ✅ 안전 | 사용 |
| react-markdown | ✅ 안전 | 사용 |
| @tanstack/react-query | ✅ 안전 | 사용 |

---

## 3. 프로젝트 디렉토리 구조

```
/data/cert-poc/
├── web/                              # Next.js 앱
│   ├── app/
│   │   ├── layout.tsx               # 루트 레이아웃 (Inter 폰트, QueryProvider)
│   │   ├── page.tsx                 # → redirect /sessions
│   │   ├── globals.css              # Tailwind + Supabase 디자인 토큰
│   │   ├── upload/
│   │   │   └── page.tsx             # 파일 업로드 페이지
│   │   ├── sessions/
│   │   │   ├── page.tsx             # 히스토리 목록
│   │   │   └── [id]/
│   │   │       ├── page.tsx         # 결과 대시보드 (핵심)
│   │   │       └── review/
│   │   │           └── page.tsx     # 리뷰 전용 뷰
│   │   └── api/
│   │       ├── upload/route.ts      # 파일 업로드 프록시
│   │       └── sessions/
│   │           ├── route.ts         # 세션 목록
│   │           └── [id]/
│   │               ├── route.ts
│   │               ├── progress/route.ts   # SSE 프록시
│   │               ├── review/route.ts
│   │               └── export/[type]/route.ts
│   ├── components/
│   │   ├── upload/
│   │   │   ├── FileDropzone.tsx     # 드래그앤드롭 업로드 존
│   │   │   └── PipelineProgress.tsx # 실시간 실행 진행률 (SSE)
│   │   ├── dashboard/
│   │   │   ├── SessionHeader.tsx    # 세션 메타 + 다운로드 버튼
│   │   │   ├── QuestionList.tsx     # 왼쪽 문항 목록 패널
│   │   │   ├── QuestionDetail.tsx   # 오른쪽 문항 상세 패널
│   │   │   ├── AnomalyCard.tsx      # 유형별 탐지 결과 카드
│   │   │   ├── MatrixView.tsx       # 문항×유형 전체 매트릭스
│   │   │   └── ReviewActionBar.tsx  # 확인/반려/보류 액션 바
│   │   └── ui/                      # shadcn/ui 컴포넌트
│   ├── lib/
│   │   ├── api.ts                   # FastAPI 클라이언트 함수
│   │   ├── sse.ts                   # SSE 커스텀 훅 (useSSE)
│   │   ├── types.ts                 # 공통 TypeScript 타입
│   │   └── constants.ts             # 유형코드-한글명 매핑
│   ├── DESIGN.md                    # Supabase 디자인 시스템 참조
│   └── package.json
│
├── api/                              # FastAPI 백엔드
│   ├── main.py                      # FastAPI 앱 + CORS 설정
│   ├── db.py                        # SQLite 스키마 + 연결 관리
│   ├── pipeline.py                  # 하이브리드 파이프라인 래퍼
│   ├── routers/
│   │   ├── upload.py                # 파일 업로드 + 파싱 엔드포인트
│   │   ├── sessions.py              # 세션 CRUD + SSE 진행률
│   │   ├── review.py                # 담당자 리뷰 액션
│   │   └── export.py                # Excel/PDF 내보내기
│   └── requirements.txt
│
├── src/                              # 기존 Python 파이프라인 (유지)
├── data/
├── prompts/
├── results/                          # 세션별 JSON 결과 저장
└── docs/
    ├── DESIGN.md                     # Supabase 디자인 시스템
    └── webapp_plan.md                # 이 문서
```

---

## 4. SQLite DB 스키마

```sql
-- 윤문 세션
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,           -- UUID
    created_at      TEXT NOT NULL,              -- ISO8601
    original_filename TEXT NOT NULL,
    file_type       TEXT NOT NULL,              -- hwp|hwpx|pdf
    status          TEXT NOT NULL DEFAULT 'uploading',
                                               -- uploading|parsing|running|done|error
    question_count  INTEGER DEFAULT 0,
    found_count     INTEGER DEFAULT 0,          -- 후처리 후 최종 탐지 수
    elapsed_seconds REAL,
    md_path         TEXT,                       -- 파싱된 마크다운 경로
    result_dir      TEXT,                       -- JSON 결과 디렉토리
    notes           TEXT DEFAULT ''
);

-- 문항별 파싱 원문
CREATE TABLE questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number    INTEGER NOT NULL,
    md_text     TEXT NOT NULL                   -- 마크다운 원문
);

-- 유형별 탐지 결과
CREATE TABLE anomaly_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number     INTEGER NOT NULL,
    type_code    TEXT NOT NULL,                 -- A01~A21
    layer        INTEGER NOT NULL,              -- 0|1|2
    found        INTEGER NOT NULL DEFAULT 0,    -- 0|1
    confidence   TEXT,                          -- high|medium|low
    issues       TEXT DEFAULT '[]',             -- JSON 직렬화
    filtered     INTEGER DEFAULT 0,             -- 후처리 필터 제거 여부
    filter_reason TEXT
);

-- 담당자 리뷰 기록
CREATE TABLE review_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    q_number    INTEGER NOT NULL,
    type_code   TEXT NOT NULL,
    reviewer    TEXT NOT NULL,
    action      TEXT NOT NULL,                 -- confirmed|rejected|pending
    comment     TEXT DEFAULT '',
    created_at  TEXT NOT NULL                  -- ISO8601
);

CREATE INDEX idx_anomaly_session ON anomaly_results(session_id);
CREATE INDEX idx_review_session ON review_actions(session_id, q_number, type_code);
```

---

## 5. FastAPI 엔드포인트 설계

```
POST   /upload                          파일 업로드 + 세션 생성 + 파이프라인 비동기 시작
GET    /sessions                        세션 목록 (페이지네이션)
GET    /sessions/{id}                   세션 상세 + 결과 요약
GET    /sessions/{id}/progress          SSE 스트림 (실시간 진행률)
GET    /sessions/{id}/results           전체 탐지 결과 (merged_filtered)
GET    /sessions/{id}/questions/{q}     문항 상세 (원문 + 해당 유형 결과 + 리뷰)
POST   /sessions/{id}/review            담당자 리뷰 저장 (확인/반려/보류 + 코멘트)
GET    /sessions/{id}/export/excel      Excel 다운로드
GET    /sessions/{id}/export/pdf        PDF 요약 레포트 다운로드
DELETE /sessions/{id}                   세션 삭제 (결과 파일 포함)
```

### SSE 이벤트 스키마
```json
{"event": "layer_start",    "layer": 0, "total_q": 20}
{"event": "q_layer0_done",  "layer": 0, "q": 1, "types": {"A01": true, "A03": false}}
{"event": "layer_done",     "layer": 0, "found": 5}
{"event": "layer_start",    "layer": 1}
{"event": "q_layer1_done",  "layer": 1, "q": 3, "group": "G1", "found_types": ["A04"]}
{"event": "layer_done",     "layer": 1, "found": 3}
{"event": "layer_start",    "layer": 2}
{"event": "q_type_done",    "layer": 2, "q": 5, "type_code": "A02", "found": true, "confidence": "high"}
{"event": "postprocess",    "filtered": 2}
{"event": "done",           "total_found": 8, "elapsed": 142.3}
{"event": "error",          "message": "..."}
```

---

## 6. UI/UX 상세 설계

### 6.1 업로드 페이지 (`/upload`)

```
┌────────────────────────────────────────────┐
│  시험지 윤문 검사                [히스토리▶] │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │                                      │  │
│  │   ↑ 파일을 드래그하거나 클릭하세요    │  │
│  │                                      │  │
│  │   HWP · HWPX · PDF 지원              │  │
│  │                                      │  │
│  └──────────────────────────────────────┘  │
│                                            │
│  ※ 파일은 로컬에서만 처리됩니다            │
└────────────────────────────────────────────┘
```
- 업로드 즉시 `/sessions/[id]`로 이동
- 배경: `canvas-soft` (#fafafa), 드롭존 border: `hairline` 1px dashed

---

### 6.2 파이프라인 진행 화면 (status: running)

```
┌────────────────────────────────────────────────────────────┐
│  정보보호개요_X.hwp — 분석 중                               │
│                                                            │
│  ✅  파일 파싱 완료           (20문항 추출)                  │
│  ▶   Layer 0 · 코드 탐지     [████████░░░░] 13/20          │
│  ○   Layer 1 · 그룹 LLM      대기 중                       │
│  ○   Layer 2 · per-type LLM  대기 중                       │
│                                                            │
│  문항별 진행                                               │
│  Q01✅ Q02✅ Q03✅ Q04▶ Q05○ Q06○ Q07○ Q08○ Q09○ Q10○    │
│  Q11○ Q12○ Q13○ Q14○ Q15○ Q16○ Q17○ Q18○ Q19○ Q20○       │
└────────────────────────────────────────────────────────────┘
```
- `progress` 컴포넌트 (shadcn): emerald (#3ecf8e)
- 완료 → 자동으로 대시보드 뷰 전환

---

### 6.3 결과 대시보드 (`/sessions/[id]`) — 핵심

**레이아웃: 좌(문항 목록) + 우(상세 패널) 2-컬럼 스플릿**

```
┌──────────────────┬─────────────────────────────────────────┐
│ [탭: 목록 | 매트릭스]│ 정보보호개요_X.hwp  탐지 8건  [Excel▼] │
├──────────────────┤─────────────────────────────────────────┤
│ Q01 ●A01 ●A13    │ ## 1.                                   │
│ Q02 —            │ 다음 중 개인정보 보호의 원칙으로         │
│ Q03 ●A04         │ 옳지 않은 것은?                         │
│ Q04 —            │                                         │
│ Q05 ●A02         │ ① 개인정보 처리 목적 명확화             │
│ Q06 —            │ ② 개인정보 처리 목적 명확화  ← 중복!    │
│ Q07 ●A07         │ ③ 최소 수집 원칙                        │
│ Q08 ●A08         │ ④ 안전한 관리                           │
│ Q09 —            │                                         │
│ Q10 ●A10         │ ─────────────────────────────────────   │
│ Q11 —            │ 탐지된 이상                             │
│ Q12 —            │                                         │
│ Q13 ●A13         │ ┌─ A01 보기 중복  [L0·코드] ●HIGH ────┐ │
│ ...              │ │ ① "개인정보 처리 목적 명확화"         │ │
│                  │ │ → 1번과 2번 선택지 내용 동일           │ │
│                  │ │                              [확인] [반려]│
│                  │ └────────────────────────────────────┘ │
│                  │                                         │
│                  │ ┌─ A13 문항번호 중복  [L0·코드] ●HIGH ─┐│
│                  │ │ 문항 1번 번호가 2회 등장               ││
│                  │ │                              [확인] [반려]│
│                  │ └────────────────────────────────────┘ │
└──────────────────┴─────────────────────────────────────────┘
```

**왼쪽 패널 — 문항 목록:**
- 높이: 화면 전체 스크롤, 고정 너비 220px
- 각 행: Q번호 + 탐지 유형 배지 (pill-tag-green, 컴팩트 2px 4px padding)
- 정상 문항: 배지 없이 `—`
- 선택된 문항: `canvas-soft` 배경 하이라이트
- 필터: [전체] [탐지만] [미검토만]

**오른쪽 패널 — 문항 상세:**
- 상단 1/3: 마크다운 원문 렌더링 (react-markdown, code-block 스타일)
- 하단 2/3: 탐지 카드 목록

**탐지 카드 (AnomalyCard) — 컴팩트:**
```
┌──────────────────────────────────────────────────┐
│ [A01] 보기 중복   [L0 코드]   ● HIGH             │
│                                                  │
│ 위치: ①번 선택지                                 │
│ 원문: "개인정보 처리 목적 명확화"                 │
│ 문제: 1번·2번 선택지 내용 동일                   │
│                                                  │
│ 담당자: [___이름___]  [확인✓]  [반려✗]  [보류?]   │
│ 코멘트: ________________________________         │
└──────────────────────────────────────────────────┘
```
- 확인 → 에메랄드 그린 테두리
- 반려 → tomato (#ff2201) 테두리
- 보류 → violet (#644fc1) 테두리
- 검토 완료 후 카드 상단 우측에 작은 배지 표시

---

### 6.4 매트릭스 뷰 (탭 전환)

```
      A01 A02 A03 A04 A05 A06 A07 A08 A09 A10 A11 A12 A13 A14 A15 A16 A17 A18 A19 A20 A21
Q01    ●   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ●   ·   ·   ·   ●   ·   ·   ·   ·
Q02    ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·
Q03    ·   ·   ·   ●   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·   ·
...
```
- `●` : found (에메랄드 #3ecf8e 도트)
- `▲` : found + filtered (노란색 #ffdb13)
- `·` : not found (hairline-cool 도트)
- `!` : error (tomato)
- 셀 hover → tooltip (type_code, confidence, issue 요약)
- 클릭 → 왼쪽 문항 선택 + 해당 유형 카드로 스크롤

---

### 6.5 히스토리 목록 (`/sessions`)

```
┌────────────────────────────────────────────────────────────┐
│ 윤문 히스토리           [검색...] [새 파일 분석 +]           │
├────┬──────────────────┬──────┬──────┬──────────┬──────────┤
│ 날짜 │ 파일명            │ 문항 │ 탐지 │ 상태     │ 작업     │
├────┼──────────────────┼──────┼──────┼──────────┼──────────┤
│ 05/29│ 정보보호개요_X.hwp │  20  │  8건 │ ✅ 완료  │ 보기│Excel│
│ 05/27│ 정보보호윤리_X.hwp │  20  │  5건 │ ✅ 완료  │ 보기│Excel│
│ 05/26│ 정보보호개요_O.hwp │  20  │  0건 │ ✅ 완료  │ 보기│Excel│
└────┴──────────────────┴──────┴──────┴──────────┴──────────┘
```
- 테이블: `hairline` 1px border, 헤더 `canvas-soft` 배경
- 행 hover: `canvas-soft` (#fafafa)
- 날짜 내림차순 정렬 기본

---

## 7. 구현 순서

### Phase 1 — 백엔드 기반 (2~3일)
1. `api/db.py` — SQLite 스키마 생성
2. `api/pipeline.py` — 기존 `src/hybrid_run.py` 래퍼 (비동기 실행, SSE 이벤트 emit)
3. `api/routers/upload.py` — 파일 업로드 + HWP/PDF 파싱 + 세션 생성
4. `api/routers/sessions.py` — 세션 CRUD + SSE 진행률 스트림
5. `api/main.py` — FastAPI 앱 조립 + CORS

### Phase 2 — Next.js 기반 (1~2일)
1. `create-next-app` + Tailwind v4 + shadcn/ui 초기화
2. `globals.css` — Supabase 디자인 토큰 CSS 변수 정의
3. `lib/api.ts`, `lib/types.ts`, `lib/sse.ts` — 공통 유틸

### Phase 3 — 업로드 + 진행률 UI (1일)
1. `FileDropzone.tsx` — 드래그앤드롭 (react-dropzone)
2. `PipelineProgress.tsx` — SSE 실시간 진행률 표시

### Phase 4 — 결과 대시보드 (3~4일, 핵심)
1. `QuestionList.tsx` — 왼쪽 문항 목록 패널
2. `QuestionDetail.tsx` — 오른쪽 상세 패널
3. `AnomalyCard.tsx` — 탐지 카드 + 리뷰 액션
4. `MatrixView.tsx` — 문항×유형 전체 매트릭스 탭

### Phase 5 — 히스토리 + 내보내기 (1~2일)
1. `/sessions` 목록 페이지
2. Excel 내보내기 (xlsx)
3. PDF 요약 레포트 (@react-pdf/renderer)

---

## 8. npm install 명령어

> 아래 명령어는 2026-05-29 기준 최신 버전 기준. 설치 후 `npm audit --audit-level=high` 로 고위험 취약점 0건 확인 필수.

### Step 1 — Next.js 프로젝트 초기화
```bash
cd /data/cert-poc
# Next.js 16 LTS (Turbopack 기본 활성화)
npx create-next-app@16 web \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"

cd web
```

### Step 2 — 핵심 의존성 설치
```bash
# UI 유틸 (보안 이슈 없음)
npm install lucide-react class-variance-authority clsx tailwind-merge

# 파일 업로드 드롭존
npm install react-dropzone

# 마크다운 렌더링 (문항 원문 표시)
npm install react-markdown remark-gfm

# 서버 상태(API 캐싱) + 클라이언트 상태(UI)
npm install @tanstack/react-query zustand

# 날짜 포맷
npm install date-fns
```

> ⛔ **설치하지 말 것**: `xlsx`, `exceljs` — 보안 취약점 또는 장기 미유지.  
> Excel/PDF 내보내기는 FastAPI 서버(openpyxl)에서 생성하고 브라우저로 파일 스트리밍.

### Step 3 — shadcn/ui 초기화 (Rhea 스타일 — 컴팩트 제품 UI)
```bash
# CLI v4 + Rhea 스타일 (컴팩트, 집중형 제품 인터페이스)
npx shadcn@4.8.2 init --style rhea

# 필요 컴포넌트 추가
npx shadcn@latest add \
  button card badge table \
  sheet dialog progress \
  toast separator tabs \
  scroll-area input textarea label
```

### Step 4 — 취약점 검사
```bash
npm audit --audit-level=high
# high/critical 0건이어야 함
```

### Python 백엔드 의존성 (api/)
```bash
cd /data/cert-poc
pip install \
  "fastapi>=0.136.1" \
  "uvicorn[standard]>=0.48.0" \
  "python-multipart>=0.0.20" \
  "sse-starlette>=2.3.0" \
  "aiofiles>=24.1.0" \
  "pdfplumber>=0.11.4" \
  "openpyxl>=3.1.5"
```

---

## 9. 컴팩트 + 강렬함 디자인 원칙

> Supabase 디자인 시스템 기반으로 **내부 업무 도구 특성**에 맞게 압축. 여백은 줄이되, 대비(contrast)와 정보 밀도로 강렬함을 만든다.

### 핵심 원칙
1. **에메랄드는 단 하나의 사건** — 화면당 filled 에메랄드 버튼 1개. 나머지는 outline 또는 ghost. 에메랄드가 희소할수록 임팩트가 강해진다.
2. **텍스트 대비로 위계** — 탐지 건수, 문항 번호 같은 핵심 숫자는 `ink` (#171717) weight 500. 보조 텍스트는 `ink-mute` (#707070). 3단계 대비만 사용.
3. **여백은 기능적으로** — 컴포넌트 내부 padding을 줄이되(8→4px), 컴포넌트 간 경계는 `hairline` 1px 라인으로 명확히 구분.
4. **색은 상태만 말한다** — 탐지=에메랄드, 에러=tomato, 보류=violet. 장식용 색 없음.
5. **타이포만으로 드라마** — 탐지 카운트(`28px weight 500`), 문항 번호(`13px ink-mute`), 탐지 유형명(`14px weight 500 ink`)의 크기 차이가 강렬함을 만든다.

### 컴팩트 치수 기준
| 요소 | 마케팅(Supabase 원본) | 앱 컴팩트 |
|------|---------------------|-----------|
| 버튼 padding | 8px 16px | 4px 10px |
| 카드 padding | 32px | 12px |
| 테이블 셀 | — | py-1.5 px-2 |
| 섹션 여백 | 64–96px | 8–16px |
| 폰트(body) | 16px | 13px |
| 폰트(caption) | 13px | 12px |
| 아이콘 | 20px | 14px |
| 배지 height | — | 18px (pill, 컴팩트) |

### 강렬함을 주는 요소
```
✦ 탐지 카운트: 숫자를 크게 (display-md 28px, weight 500, ink)
✦ 상태 전환: found → 에메랄드 left-border 4px (카드 왼쪽 액센트 라인)
✦ 매트릭스: 흰 배경에 채워진 에메랄드 도트 — 나머지 셀은 비어 보임
✦ 리뷰 확인: 확인 클릭 시 카드 전체 에메랄드 left-border 순간 전환
✦ 레이어 배지: L0(코드)=canvas-night 배경, L1=violet, L2=indigo — 층위 즉시 식별
✦ 탐지 문항 행: 왼쪽 패널에서 탐지 문항 행에만 에메랄드 left-accent dot(6px)
```

### 절대 금지
- 배경 그라디언트 (흰 캔버스가 디자인)
- 둥근 버튼 (radius 최대 6px)
- 초록 이외의 filled 버튼
- 그림자 과다 사용 (카드 기본: hairline 1px only, hover: Level 1 shadow)
- 애니메이션 과용 (상태 전환 150ms max)

---

## 9. 디자인 토큰 (globals.css)

```css
/* Supabase DESIGN.md 기반 컴팩트 앱 변형 */
:root {
  --color-primary:       #3ecf8e;
  --color-primary-deep:  #24b47e;
  --color-ink:           #171717;
  --color-ink-mute:      #707070;
  --color-ink-faint:     #b2b2b2;
  --color-canvas:        #ffffff;
  --color-canvas-soft:   #fafafa;
  --color-canvas-night:  #1c1c1c;
  --color-hairline:      #dfdfdf;
  --color-hairline-cool: #ededed;
  --color-found:         #3ecf8e;   /* 탐지됨 */
  --color-filtered:      #ffdb13;   /* 필터 제거됨 */
  --color-error:         #ff2201;   /* 에러 */
  --color-confirmed:     #3ecf8e;   /* 리뷰: 확인 */
  --color-rejected:      #ff2201;   /* 리뷰: 반려 */
  --color-pending:       #644fc1;   /* 리뷰: 보류 */
}
```

---

## 10. 실행 방법 (개발)

```bash
# 터미널 1: FastAPI 백엔드
cd /data/cert-poc/api
uvicorn main:app --reload --port 8000

# 터미널 2: Next.js 프론트엔드
cd /data/cert-poc/web
npm run dev
# → http://localhost:3000

# 터미널 3: 로컬 LLM (기존)
# llama.cpp 서버 :8081 (EXAONE-3.5-32B)
```

---

## 11. 향후 고려사항

- **HWPX 내보내기**: kordoc 역방향 변환 또는 별도 라이브러리 조사 필요
- **PDF 파싱 정확도**: pdfplumber로 ## N. 형식 추출 시 레이아웃 복잡도에 따라 정확도 편차 존재
- **다중 사용자**: 현재 담당자명을 텍스트로 입력하는 방식 → 추후 간단한 세션 인증 추가 가능
- **파이프라인 취소**: SSE 연결 종료 시 실행 중인 파이프라인 중단 시그널 처리 필요
- **결과 캐시**: 동일 파일 재업로드 시 기존 세션 재사용 여부 선택 옵션
