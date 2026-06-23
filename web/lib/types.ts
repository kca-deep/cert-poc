/**
 * Domain types — webapp_frontend_plan.md §3.
 * Mirrors the pipeline output schema (prompts/_shared/output_schema.json)
 * and the planned DB schema (webapp_plan §4). Server I/O is isolated in
 * lib/api.ts so these stay backend-agnostic (mock now, FastAPI later).
 */

export type SessionStatus =
  | "uploading"
  | "parsing"
  | "running"
  | "done"
  | "error";

/** holistic finding 신뢰도 (LLM 한글 enum). */
export type Confidence = "높음" | "보통" | "낮음";

/** holistic error_type 11-enum (prompts/_shared/output_schema.json 미러). */
export type ErrorType =
  | "맞춤법"
  | "띄어쓰기"
  | "문법비문"
  | "선택지누락"
  | "선택지중복"
  | "용어오류"
  | "사실오류"
  | "약어오기"
  | "정답유출"
  | "편집표시"
  | "기타";

export type ReviewActionType = "confirmed" | "rejected" | "pending";

export type FileType = "hwp" | "hwpx" | "pdf";

/** LLM 공급자 — 내부망 로컬 모델 vs Claude Haiku. */
export type LlmProvider = "local" | "claude";

/** GET /config/llm 응답 — 토글 초기 상태/가용성 메타. */
export interface ProviderMeta {
  id: LlmProvider;
  label: string;
  model: string;
  available: boolean;
  // local(Ollama) 전용: 모델이 메모리에 로딩(=실행중)됐는지. null=무관/구버전 응답.
  loaded?: boolean | null;
  // 탐지된 백엔드 종류: "ollama" | "openai" | null.
  backend?: string | null;
}

export interface LlmConfig {
  default: LlmProvider;
  claudeConfigured: boolean;
  providers: ProviderMeta[];
}

export interface Session {
  id: string;
  createdAt: string; // ISO 8601
  originalFilename: string;
  fileType: FileType;
  status: SessionStatus;
  questionCount: number;
  foundCount: number;
  elapsedSeconds?: number;
  provider?: LlmProvider;
  model?: string | null; // 분석 시점 실제 모델 id (gpt-oss/exaone 구분), 구 세션은 null
}

export interface Question {
  qNumber: number;
  mdText: string;
}

/**
 * holistic 검출 오류 1건 (src/core/events.py Finding 미러, camelCase).
 * id 는 세션 내 안정 식별자 "<q>-<index>" — 검수(ReviewAction)의 PK.
 */
export interface Finding {
  id: string;
  qNumber: number;
  location: string; // 자유 서술 (예: "발문", "지문", "보기 ②")
  quote: string; // 문항 원문 인용
  errorType: ErrorType;
  reason: string;
  suggestion: string;
  confidence: Confidence;
}

export interface ReviewAction {
  findingId: string;
  reviewer?: string;
  action: ReviewActionType;
  comment?: string;
}

/** SSE progress union — src/core/events.py 미러 (무변환 소비). */
export type ProgressEvent =
  | { event: "start"; totalQ: number }
  | { event: "q_start"; q: number; worker: number }
  | {
      event: "q_done";
      q: number;
      hasError: boolean;
      findings: Finding[];
      elapsedSeconds?: number;
      error?: string; // 있으면 검토 실패(타임아웃/파싱오류) — 무오류 완료와 구분
    }
  | { event: "done"; totalFound: number; elapsed: number }
  | { event: "error"; message: string };

/* --- Derived view models (frontend-only) --- */

/** Full payload for the dashboard route. */
export interface SessionDetail {
  session: Session;
  questions: Question[];
  findings: Finding[];
}

/** A question paired with its findings — convenience for QuestionList/Detail. */
export interface QuestionWithFindings {
  question: Question;
  findings: Finding[];
}

/* --- Upload / parse view models --- */

export type ParseWarningSeverity = "warning" | "info";

/** A pre-analysis sanity check surfaced after parsing (보기 누락 등). */
export interface ParseWarning {
  qNumber?: number;
  severity: ParseWarningSeverity;
  message: string;
}

/** Result of parsing an uploaded file into markdown (api.parseUpload). */
export interface ParseResult {
  filename: string;
  fileType: FileType;
  sizeBytes: number;
  questionCount: number;
  questions: Question[];
  mergedMd: string; // full parsed markdown (for raw preview)
  warnings: ParseWarning[];
}
