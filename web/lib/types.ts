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

export type Layer = 0 | 1 | 2;
export type Confidence = "low" | "medium" | "high";

export type IssueLocation =
  | "stem"
  | "passage"
  | "choice_1"
  | "choice_2"
  | "choice_3"
  | "choice_4";

export type ReviewActionType = "confirmed" | "rejected" | "pending";

export type FileType = "hwp" | "hwpx" | "pdf";

/** LLM 공급자 — 내부망 로컬 모델(EXAONE 등) vs Claude Haiku. */
export type LlmProvider = "local" | "claude";

/** GET /config/llm 응답 — 토글 초기 상태/가용성 메타. */
export interface ProviderMeta {
  id: LlmProvider;
  label: string;
  model: string;
  available: boolean;
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

export interface Issue {
  location: IssueLocation;
  original: string;
  suspected: string;
  suggested?: string | null;
  extra?: Record<string, unknown>;
}

export interface AnomalyResult {
  qNumber: number;
  typeCode: string; // e.g. "A04"
  layer: Layer;
  found: boolean;
  confidence?: Confidence;
  issues: Issue[];
  filtered?: boolean;
  filterReason?: string;
}

export interface ReviewAction {
  qNumber: number;
  typeCode: string;
  reviewer?: string;
  action: ReviewActionType;
  comment?: string;
}

/** SSE progress union — webapp_plan §5 (consumed in step 6). */
export type ProgressEvent =
  | { event: "layer_start"; layer: Layer; totalQ?: number }
  | { event: "q_layer0_done"; q: number; types: Record<string, boolean> }
  | {
      event: "q_type_done";
      layer: Layer;
      q: number;
      typeCode: string;
      found: boolean;
      confidence?: Confidence;
    }
  | { event: "layer_done"; layer: Layer; found: number }
  | { event: "postprocess"; filtered: number }
  | { event: "done"; totalFound: number; elapsed: number }
  | { event: "error"; message: string };

/* --- Derived view models (frontend-only) --- */

/** Full payload for the dashboard route. */
export interface SessionDetail {
  session: Session;
  questions: Question[];
  results: AnomalyResult[];
}

/** A question paired with its detections — convenience for QuestionList/Detail. */
export interface QuestionWithResults {
  question: Question;
  results: AnomalyResult[];
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
