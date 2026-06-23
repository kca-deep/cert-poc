"use client";

/**
 * 검수 결정(확인/반려/보류) 훅 — 서버(DB review_actions) 영속.
 * 컴포넌트는 USE_MOCK 분기를 알 필요 없이 이 훅만 쓴다 (분기는 lib/api.ts 내부).
 * mock 모드에서는 api.ts 가 zustand(localStorage)로 위임한다.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listReviews, queryKeys, upsertReview } from "@/lib/api";
import type { ReviewAction } from "@/lib/types";

/** 세션의 검수 결정을 findingId → ReviewAction 맵으로 반환. */
export function useReviews(sessionId: string): Map<string, ReviewAction> {
  const { data } = useQuery({
    queryKey: queryKeys.reviews(sessionId),
    queryFn: () => listReviews(sessionId),
    staleTime: 60_000,
  });

  const map = new Map<string, ReviewAction>();
  for (const r of data ?? []) map.set(r.findingId, r);
  return map;
}

/** 검수 결정 upsert 뮤테이션 (낙관적 업데이트 + 롤백). */
export function useSetReview(sessionId: string) {
  const qc = useQueryClient();
  const key = queryKeys.reviews(sessionId);

  return useMutation({
    mutationFn: (r: ReviewAction) => upsertReview(sessionId, r),
    onMutate: async (r) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<ReviewAction[]>(key);
      qc.setQueryData<ReviewAction[]>(key, (old) => {
        const list = old ? [...old] : [];
        const i = list.findIndex((x) => x.findingId === r.findingId);
        if (i >= 0) list[i] = r;
        else list.push(r);
        return list;
      });
      return { prev };
    },
    onError: (_e, _r, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
