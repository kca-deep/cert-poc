"use client";

import { ArrowRight, Check, Minus, X } from "lucide-react";

import {
  CONFIDENCE_LABEL,
  LOCATION_LABEL,
  REVIEW_META,
  typeMeta,
} from "@/lib/constants";
import type { AnomalyResult, ReviewActionType } from "@/lib/types";
import { useReviews, useSetReview } from "@/lib/hooks/reviews";
import { cn } from "@/lib/utils";

import { LayerBadge } from "./LayerBadge";

const ACTIONS: {
  value: ReviewActionType;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { value: "confirmed", icon: Check },
  { value: "rejected", icon: X },
  { value: "pending", icon: Minus },
];

export function AnomalyCard({
  sessionId,
  result,
}: {
  sessionId: string;
  result: AnomalyResult;
}) {
  const meta = typeMeta(result.typeCode);

  // 검수 결정은 서버(DB review_actions)에 영속. (mock 모드는 localStorage 위임)
  const reviews = useReviews(sessionId);
  const setReview = useSetReview(sessionId);
  const action = reviews.get(`${result.qNumber}:${result.typeCode}`)?.action;

  const accent =
    action && action in REVIEW_META
      ? `var(${REVIEW_META[action].varName})`
      : "transparent";

  return (
    <div
      className="rounded-md border border-border bg-card transition-colors hover:border-border/80"
      style={{ borderLeft: `3px solid ${accent}` }}
    >
      {/* header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/60 px-3 py-2">
        <span className="font-mono text-xs font-semibold text-foreground">
          {result.typeCode}
        </span>
        <span className="text-[13px] font-medium text-foreground">
          {meta.label}
        </span>
        <LayerBadge layer={result.layer} />
        {result.confidence && (
          <span className="font-mono text-[10px] text-muted-foreground">
            신뢰도 {CONFIDENCE_LABEL[result.confidence]}
          </span>
        )}
        {result.filtered && (
          <span
            className="rounded-md px-1.5 py-0.5 text-[10px] font-medium"
            style={{
              color: "var(--status-filtered)",
              backgroundColor: "color-mix(in oklab, var(--status-filtered) 14%, transparent)",
            }}
            title={result.filterReason}
          >
            후처리 보류
          </span>
        )}
      </div>

      {/* issues */}
      <div className="flex flex-col gap-2.5 px-3 py-2.5">
        {result.issues.map((issue, i) => (
          <div key={i} className="text-[13px]">
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
              {LOCATION_LABEL[issue.location]}
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-xs">
              <span className="rounded bg-[color-mix(in_oklab,var(--status-error)_12%,transparent)] px-1.5 py-0.5 text-[var(--status-error)] line-through decoration-[var(--status-error)]/50">
                {issue.original}
              </span>
              {issue.suggested && (
                <>
                  <ArrowRight className="size-3 text-muted-foreground" />
                  <span className="rounded bg-[color-mix(in_oklab,var(--status-found)_14%,transparent)] px-1.5 py-0.5 text-[var(--status-found)]">
                    {issue.suggested}
                  </span>
                </>
              )}
            </div>
            <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
              {issue.suspected}
            </p>
          </div>
        ))}
      </div>

      {/* review actions — 세그먼트 토글(단일 선택). 테두리/분할선으로 본문과 구분,
          선택 세그먼트는 의미색으로 채워 한눈에 결정 상태가 보인다. */}
      <div className="border-t border-border/60 px-3 py-2.5">
        <div
          role="radiogroup"
          aria-label="검수 결정"
          className="flex w-full divide-x divide-border overflow-hidden rounded-md border border-border"
        >
          {ACTIONS.map(({ value, icon: Icon }) => {
            const active = action === value;
            const color = `var(${REVIEW_META[value].varName})`;
            // 확인(밝은 에메랄드)엔 어두운 글씨, 반려/보류엔 흰 글씨로 대비 확보.
            const fg =
              value === "confirmed" ? "var(--primary-foreground)" : "#ffffff";
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() =>
                  setReview.mutate({
                    qNumber: result.qNumber,
                    typeCode: result.typeCode,
                    action: value,
                  })
                }
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 px-2 py-1.5 text-[12px] font-medium transition-colors",
                  !active &&
                    "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                )}
                style={
                  active
                    ? ({ backgroundColor: color, color: fg } as React.CSSProperties)
                    : undefined
                }
              >
                <Icon className="size-3.5" />
                {REVIEW_META[value].label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
