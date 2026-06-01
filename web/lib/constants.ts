/**
 * Catalog + display metadata — webapp_frontend_plan.md §2.
 * Anomaly types A01~A21 with their layer (L0 code / L1 / L2) and group.
 * Layer/status colors reference the CSS tokens defined in app/globals.css.
 */

import type {
  Confidence,
  IssueLocation,
  Layer,
  ReviewActionType,
  SessionStatus,
} from "./types";

export interface AnomalyTypeMeta {
  code: string;
  label: string; // 한글명
  layer: Layer;
  group: string | null; // G1~G5 or null
}

/** Insertion order = display order (A01 → A21). */
export const ANOMALY_TYPES: Record<string, AnomalyTypeMeta> = {
  A01: { code: "A01", label: "보기 중복", layer: 0, group: null },
  A02: { code: "A02", label: "오자", layer: 2, group: null },
  A03: { code: "A03", label: "보기개수 미달", layer: 0, group: null },
  A04: { code: "A04", label: "맞춤법 오류", layer: 1, group: "G1" },
  A05: { code: "A05", label: "영문 오타", layer: 1, group: "G1" },
  A06: { code: "A06", label: "띄어쓰기 오류", layer: 1, group: "G1" },
  A07: { code: "A07", label: "특수기호 누락", layer: 2, group: null },
  A08: { code: "A08", label: "매끄럽지 못한 문장", layer: 2, group: null },
  A09: { code: "A09", label: "법령명 오류", layer: 1, group: "G4" },
  A10: { code: "A10", label: "오타·보기 누락", layer: 2, group: null },
  A11: { code: "A11", label: "낙서형 1", layer: 1, group: "G5" },
  A12: { code: "A12", label: "낙서형 2", layer: 2, group: null },
  A13: { code: "A13", label: "문항번호 중복", layer: 0, group: null },
  A14: { code: "A14", label: "정답 노출", layer: 1, group: "G5" },
  A15: { code: "A15", label: "보기 없음", layer: 0, group: null },
  A16: { code: "A16", label: "탈자", layer: 2, group: null },
  A17: { code: "A17", label: "지문 원문자 탈자", layer: 0, group: null },
  A18: { code: "A18", label: "문장 전체 생략", layer: 0, group: null },
  A19: { code: "A19", label: "특수기호 누락(지문)", layer: 2, group: null },
  A20: { code: "A20", label: "법조항 오류", layer: 1, group: "G4" },
  A21: { code: "A21", label: "잘못된 단어", layer: 2, group: null },
};

/** Stable A01→A21 order for matrix columns / iteration. */
export const ANOMALY_TYPE_ORDER = Object.keys(ANOMALY_TYPES);

export function typeMeta(code: string): AnomalyTypeMeta {
  return (
    ANOMALY_TYPES[code] ?? { code, label: code, layer: 2, group: null }
  );
}

/** Layer badge metadata — colors are CSS vars (see globals.css). */
export const LAYER_META: Record<
  Layer,
  { label: string; short: string; varName: string }
> = {
  0: { label: "L0 · 코드", short: "L0", varName: "--layer-0" },
  1: { label: "L1 · 추론", short: "L1", varName: "--layer-1" },
  2: { label: "L2 · 검증", short: "L2", varName: "--layer-2" },
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  low: "낮음",
  medium: "보통",
  high: "높음",
};

export const STATUS_META: Record<
  SessionStatus,
  { label: string; tone: "neutral" | "active" | "done" | "error" }
> = {
  uploading: { label: "업로드 중", tone: "neutral" },
  parsing: { label: "파싱 중", tone: "active" },
  running: { label: "분석 중", tone: "active" },
  done: { label: "완료", tone: "done" },
  error: { label: "오류", tone: "error" },
};

export const REVIEW_META: Record<
  ReviewActionType,
  { label: string; varName: string }
> = {
  confirmed: { label: "확인", varName: "--status-found" },
  rejected: { label: "반려", varName: "--status-error" },
  pending: { label: "보류", varName: "--status-hold" },
};

export const LOCATION_LABEL: Record<IssueLocation, string> = {
  stem: "발문",
  passage: "지문",
  choice_1: "보기 ①",
  choice_2: "보기 ②",
  choice_3: "보기 ③",
  choice_4: "보기 ④",
};
