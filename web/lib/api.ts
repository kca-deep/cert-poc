/**
 * Server I/O boundary — webapp_frontend_plan.md §0 data strategy.
 * Everything the UI needs from a backend goes through here so the FastAPI
 * swap (step 8) touches only this file. Toggle with NEXT_PUBLIC_USE_MOCK.
 */

import type {
  LlmConfig,
  LlmProvider,
  ParseResult,
  ReviewAction,
  Session,
  SessionDetail,
} from "./types";
import { mockReviewStore } from "./stores/review";
import {
  addMockSession,
  completeMockSession,
  deleteMockSession,
  getMockSessionDetail,
  getMockSessions,
} from "./mock/fixtures";
import { mockParse } from "./mock/parse";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false"; // mock by default

/** FastAPI base URL (used only when USE_MOCK is false). */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Small artificial latency so loading states are exercised in dev. */
function delay<T>(value: T, ms = 250): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export async function listSessions(): Promise<Session[]> {
  if (USE_MOCK) return delay(getMockSessions());

  const res = await fetch(`${API_BASE}/sessions`, { cache: "no-store" });
  if (!res.ok) throw new Error(`listSessions failed: ${res.status}`);
  return res.json();
}

export async function getSession(id: string): Promise<SessionDetail | null> {
  if (USE_MOCK) return delay(getMockSessionDetail(id));

  const res = await fetch(`${API_BASE}/sessions/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`getSession failed: ${res.status}`);
  return res.json();
}

/**
 * Parse an uploaded file into markdown + question list (pre-analysis step).
 * Mock reads `.md` directly and synthesises everything else.
 */
export async function parseUpload(file: File): Promise<ParseResult> {
  if (USE_MOCK) return delay(mockParse(file), 600);

  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload?mode=parse`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`parseUpload failed: ${res.status}`);
  return res.json();
}

/**
 * Kick off the 윤문(검수) analysis from a parsed result. Returns the new
 * session id; the dashboard then polls/streams progress.
 */
export async function startAnalysis(
  parsed: ParseResult,
  provider?: LlmProvider
): Promise<string> {
  if (USE_MOCK) {
    const id = `u${mockIdCounter()}`;
    const session: Session = {
      id,
      createdAt: nowIso(),
      originalFilename: parsed.filename,
      fileType: parsed.fileType,
      status: "running",
      questionCount: parsed.questionCount,
      foundCount: 0,
      elapsedSeconds: 0,
      provider,
    };
    addMockSession({ session, questions: parsed.questions, results: [] });
    return delay(id, 300);
  }

  // Send the full ParseResult so the backend can persist questions + md_text
  // and drive run_pipeline (see api/routers/sessions.py CreateSessionRequest).
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: parsed.filename,
      fileType: parsed.fileType,
      questionCount: parsed.questionCount,
      questions: parsed.questions,
      mergedMd: parsed.mergedMd,
      provider,
    }),
  });
  if (!res.ok) throw new Error(`startAnalysis failed: ${res.status}`);
  const { id } = await res.json();
  return id;
}

/**
 * Delete a session and all of its data (questions/results/reviews cascade).
 * A 404 is treated as success (already gone) so the list just refreshes.
 */
export async function deleteSession(id: string): Promise<void> {
  if (USE_MOCK) {
    deleteMockSession(id);
    return delay(undefined, 200);
  }
  const res = await fetch(`${API_BASE}/sessions/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) {
    throw new Error(`deleteSession failed: ${res.status}`);
  }
}

/**
 * Re-run analysis for an existing session (no re-upload), optionally switching
 * the LLM provider. Used when the local LLM was unreachable and the run errored
 * — the user flips to Claude Haiku and retries. Backend reuses stored md_text.
 */
export async function rerunAnalysis(
  id: string,
  provider?: LlmProvider
): Promise<void> {
  if (USE_MOCK) {
    completeMockSession(id, 0, 0); // mock: no real re-run; reset stub
    return delay(undefined, 200);
  }
  const res = await fetch(`${API_BASE}/sessions/${id}/rerun`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (!res.ok) throw new Error(`rerunAnalysis failed: ${res.status}`);
}

/** Available LLM providers + default + whether Claude is configured. */
export async function getLlmConfig(): Promise<LlmConfig | null> {
  if (USE_MOCK) {
    return delay({
      default: "local",
      claudeConfigured: true,
      clovaxConfigured: true,
      providers: [
        { id: "local", label: "로컬 LLM", model: "exaone-3.5-32b", available: true },
        { id: "claude", label: "Claude Haiku", model: "claude-haiku-4-5", available: true },
        { id: "clovax", label: "HyperCLOVA X", model: "HCX-005", available: true },
      ],
    });
  }
  try {
    const res = await fetch(`${API_BASE}/config/llm`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null; // 서버 미연결 — 토글은 로컬 상태로만 동작
  }
}

/**
 * Mark a mock analysis session done with the given findings count. Called by
 * the progress hook's onDone in mock mode; the real backend owns this server-side.
 */
export function completeAnalysis(
  id: string,
  foundCount: number,
  elapsedSeconds: number
): void {
  if (USE_MOCK) completeMockSession(id, foundCount, elapsedSeconds);
}

/**
 * 검수 결정(확인/반려/보류) 영속 I/O. real 모드는 DB(review_actions)에,
 * mock 모드는 zustand(localStorage) 스토어에 저장한다.
 */
export async function listReviews(sessionId: string): Promise<ReviewAction[]> {
  if (USE_MOCK) return delay(mockReviewStore.list(sessionId), 50);

  const res = await fetch(`${API_BASE}/sessions/${sessionId}/reviews`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`listReviews failed: ${res.status}`);
  return res.json();
}

export async function upsertReview(
  sessionId: string,
  review: ReviewAction
): Promise<void> {
  if (USE_MOCK) {
    mockReviewStore.upsert(sessionId, review);
    return delay(undefined, 50);
  }
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/reviews`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(review),
  });
  if (!res.ok) throw new Error(`upsertReview failed: ${res.status}`);
}

/**
 * 검수 '확인' 항목만 검증결과 파일(Excel/PDF)로 내려받는다. 백엔드가 파일명
 * (원본문서명_timestamp_검증결과.{xlsx|pdf})과 바이트를 만들어 주므로, 여기서는
 * blob 과 Content-Disposition 파일명을 반환만 한다. 확인 항목이 없으면(400) 등
 * 오류 응답은 detail 메시지로 throw 한다. mock 모드는 백엔드 의존이라 미지원.
 */
export async function exportReviews(
  sessionId: string,
  format: "xlsx" | "pdf"
): Promise<{ blob: Blob; filename: string }> {
  if (USE_MOCK) {
    throw new Error("내보내기는 백엔드 연결 후 제공됩니다.");
  }
  const res = await fetch(
    `${API_BASE}/sessions/${sessionId}/export?format=${format}`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    const msg = await res
      .json()
      .then((j) => j?.detail as string | undefined)
      .catch(() => undefined);
    throw new Error(msg ?? `내보내기 실패: ${res.status}`);
  }
  const blob = await res.blob();
  const filename =
    parseContentDispositionFilename(res.headers.get("Content-Disposition")) ??
    `검증결과.${format}`;
  return { blob, filename };
}

/** Content-Disposition 에서 filename*(RFC 5987) 우선, 없으면 filename 파싱. */
function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* fall through */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  if (plain) {
    try {
      return decodeURIComponent(plain[1]);
    } catch {
      return plain[1];
    }
  }
  return null;
}

let _mockId = 0;
function mockIdCounter(): number {
  return ++_mockId;
}

// `new Date()` is fine in the browser (client-only call path).
function nowIso(): string {
  return new Date().toISOString();
}

/* React Query keys — keep colocated so callers stay consistent. */
export const queryKeys = {
  sessions: ["sessions"] as const,
  session: (id: string) => ["session", id] as const,
  llmConfig: ["llmConfig"] as const,
  reviews: (id: string) => ["reviews", id] as const,
};
