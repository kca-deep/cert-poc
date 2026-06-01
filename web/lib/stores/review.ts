/**
 * Reviewer decisions — webapp_frontend_plan.md §0 (revisit-able UX).
 * Persisted to localStorage so confirm/reject/hold survive reload and
 * re-visiting a session. Keyed per session, then per (qNumber:typeCode).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ReviewAction, ReviewActionType } from "../types";

export interface ReviewEntry {
  action: ReviewActionType;
  comment?: string;
}

type SessionReviews = Record<string, ReviewEntry>; // key: `${qNumber}:${typeCode}`

interface ReviewState {
  bySession: Record<string, SessionReviews>;
  setAction: (
    sessionId: string,
    qNumber: number,
    typeCode: string,
    action: ReviewActionType
  ) => void;
  setComment: (
    sessionId: string,
    qNumber: number,
    typeCode: string,
    comment: string
  ) => void;
  clear: (sessionId: string, qNumber: number, typeCode: string) => void;
}

const reviewKey = (qNumber: number, typeCode: string) =>
  `${qNumber}:${typeCode}`;

export const useReviewStore = create<ReviewState>()(
  persist(
    (set) => ({
      bySession: {},
      setAction: (sessionId, qNumber, typeCode, action) =>
        set((state) => {
          const key = reviewKey(qNumber, typeCode);
          const session = state.bySession[sessionId] ?? {};
          const prev = session[key];
          return {
            bySession: {
              ...state.bySession,
              [sessionId]: { ...session, [key]: { ...prev, action } },
            },
          };
        }),
      setComment: (sessionId, qNumber, typeCode, comment) =>
        set((state) => {
          const key = reviewKey(qNumber, typeCode);
          const session = state.bySession[sessionId] ?? {};
          const prev = session[key] ?? { action: "pending" as ReviewActionType };
          return {
            bySession: {
              ...state.bySession,
              [sessionId]: { ...session, [key]: { ...prev, comment } },
            },
          };
        }),
      clear: (sessionId, qNumber, typeCode) =>
        set((state) => {
          const key = reviewKey(qNumber, typeCode);
          const session = { ...(state.bySession[sessionId] ?? {}) };
          delete session[key];
          return {
            bySession: { ...state.bySession, [sessionId]: session },
          };
        }),
    }),
    { name: "cert-review-store" }
  )
);

/** Selector helper for a single detection's review entry. */
export function selectReview(
  state: ReviewState,
  sessionId: string,
  qNumber: number,
  typeCode: string
): ReviewEntry | undefined {
  return state.bySession[sessionId]?.[reviewKey(qNumber, typeCode)];
}

/**
 * Mock 모드 백엔드 어댑터 — 검수 결정 영속을 zustand(localStorage)로 처리.
 * real 모드는 lib/api.ts 가 DB(review_actions) 엔드포인트를 사용하고, 이 어댑터는
 * NEXT_PUBLIC_USE_MOCK=true 일 때만 호출된다 (lib/api.ts listReviews/upsertReview).
 * React 외부에서 store 에 접근하므로 getState() 를 쓴다.
 */
export const mockReviewStore = {
  list(sessionId: string): ReviewAction[] {
    const bySession = useReviewStore.getState().bySession[sessionId] ?? {};
    return Object.entries(bySession).map(([key, entry]) => {
      const [q, typeCode] = key.split(":");
      return {
        qNumber: Number(q),
        typeCode,
        action: entry.action,
        comment: entry.comment,
      };
    });
  },
  upsert(sessionId: string, r: ReviewAction): void {
    const st = useReviewStore.getState();
    st.setAction(sessionId, r.qNumber, r.typeCode, r.action);
    if (r.comment != null) {
      st.setComment(sessionId, r.qNumber, r.typeCode, r.comment);
    }
  },
};
