/**
 * Reviewer decisions — 검수 결정(확인/반려/보류) 영속 (finding 단위).
 * Persisted to localStorage so decisions survive reload. Keyed per session,
 * then per findingId ("<q>-<index>").
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ReviewAction, ReviewActionType } from "../types";

export interface ReviewEntry {
  action: ReviewActionType;
  comment?: string;
}

type SessionReviews = Record<string, ReviewEntry>; // key: findingId

interface ReviewState {
  bySession: Record<string, SessionReviews>;
  setAction: (
    sessionId: string,
    findingId: string,
    action: ReviewActionType
  ) => void;
  setComment: (sessionId: string, findingId: string, comment: string) => void;
  clear: (sessionId: string, findingId: string) => void;
}

export const useReviewStore = create<ReviewState>()(
  persist(
    (set) => ({
      bySession: {},
      setAction: (sessionId, findingId, action) =>
        set((state) => {
          const session = state.bySession[sessionId] ?? {};
          const prev = session[findingId];
          return {
            bySession: {
              ...state.bySession,
              [sessionId]: { ...session, [findingId]: { ...prev, action } },
            },
          };
        }),
      setComment: (sessionId, findingId, comment) =>
        set((state) => {
          const session = state.bySession[sessionId] ?? {};
          const prev = session[findingId] ?? { action: "pending" as ReviewActionType };
          return {
            bySession: {
              ...state.bySession,
              [sessionId]: { ...session, [findingId]: { ...prev, comment } },
            },
          };
        }),
      clear: (sessionId, findingId) =>
        set((state) => {
          const session = { ...(state.bySession[sessionId] ?? {}) };
          delete session[findingId];
          return {
            bySession: { ...state.bySession, [sessionId]: session },
          };
        }),
    }),
    { name: "cert-review-store" }
  )
);

/** Selector helper for a single finding's review entry. */
export function selectReview(
  state: ReviewState,
  sessionId: string,
  findingId: string
): ReviewEntry | undefined {
  return state.bySession[sessionId]?.[findingId];
}

/**
 * Mock 모드 백엔드 어댑터 — 검수 결정 영속을 zustand(localStorage)로 처리.
 * real 모드는 lib/api.ts 가 DB(review_actions) 엔드포인트를 사용한다.
 */
export const mockReviewStore = {
  list(sessionId: string): ReviewAction[] {
    const bySession = useReviewStore.getState().bySession[sessionId] ?? {};
    return Object.entries(bySession).map(([findingId, entry]) => ({
      findingId,
      action: entry.action,
      comment: entry.comment,
    }));
  },
  upsert(sessionId: string, r: ReviewAction): void {
    const st = useReviewStore.getState();
    st.setAction(sessionId, r.findingId, r.action);
    if (r.comment != null) {
      st.setComment(sessionId, r.findingId, r.comment);
    }
  },
};
