"use client";

import { ArrowRight, Check, Minus, X } from "lucide-react";

import { CONFIDENCE_META, REVIEW_META, errorTypeMeta } from "@/lib/constants";
import type { Finding, ReviewActionType } from "@/lib/types";
import { useReviews, useSetReview } from "@/lib/hooks/reviews";
import { cn } from "@/lib/utils";

import { ErrorTypeChip } from "./ErrorTypeChip";

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
  finding,
}: {
  sessionId: string;
  finding: Finding;
}) {
  const meta = errorTypeMeta(finding.errorType);
  const conf = CONFIDENCE_META[finding.confidence];

  // 검수 결정은 서버(DB review_actions)에 영속. (mock 모드는 localStorage 위임)
  const reviews = useReviews(sessionId);
  const setReview = useSetReview(sessionId);
  const action = reviews.get(finding.id)?.action;

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
        <ErrorTypeChip errorType={finding.errorType} />
        <span className="text-[13px] text-muted-foreground">
          {finding.location}
        </span>
        {conf && (
          <span
            className="ml-auto font-mono text-[11px]"
            style={{ color: `var(${conf.tone})` }}
          >
            신뢰도 {conf.label}
          </span>
        )}
      </div>

      {/* finding body */}
      <div className="flex flex-col gap-2.5 px-3 py-2.5 text-[13px]">
        {/* quote → suggestion */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[13px]">
          {/* 원문(quote): 글씨는 중립색으로 읽기 쉽게, 빨간 좌측바+취소선으로 '틀린 원문' 표시 */}
          <span className="rounded border-l-2 border-[var(--status-error)] bg-[color-mix(in_oklab,var(--status-error)_10%,transparent)] px-1.5 py-0.5 text-foreground line-through decoration-[var(--status-error)]">
            {finding.quote}
          </span>
          {finding.suggestion && (
            <>
              <ArrowRight className="size-3 text-muted-foreground" />
              {/* 제안(fix): 글씨는 중립색, 유형색은 옅은 배경 틴트로만 (가독성 + 유형 식별) */}
              <span
                className="rounded px-1.5 py-0.5 text-foreground"
                style={{
                  backgroundColor: `color-mix(in oklab, ${meta.color} 16%, transparent)`,
                }}
              >
                {finding.suggestion}
              </span>
            </>
          )}
        </div>
        {/* reason */}
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          {finding.reason}
        </p>
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
                    findingId: finding.id,
                    action: value,
                  })
                }
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 px-2 py-1.5 text-[13px] font-medium transition-colors",
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
