"use client";

/**
 * PipelineProgress — visualizes the live state of the 3-layer analysis pipeline.
 * Purely presentational: receives a ProgressState prop and renders it.
 * No timers, no simulation. Intended for the "분석 중" session view.
 */

import type { LayerProgress, ProgressState } from "@/lib/sse";
import { LayerBadge } from "@/components/dashboard/LayerBadge";
import { ANOMALY_TYPES, ANOMALY_TYPE_ORDER, typeMeta } from "@/lib/constants";
import { Progress } from "@/components/ui/progress";
import { PipelineGuideLink } from "@/components/pipeline/PipelineGuideLink";
import { Check, Circle, Loader2 } from "lucide-react";

// ─── helpers ────────────────────────────────────────────────────────────────

const LAYER_LABELS: Record<0 | 1 | 2, string> = {
  0: "코드 탐지",
  1: "그룹 LLM",
  2: "per-type LLM",
};

// 레이어별 한글 유형명 — constants 카탈로그(layer 필드)에서 파생(단일 소스).
const LAYER_TYPE_LABELS: Record<0 | 1 | 2, string[]> = { 0: [], 1: [], 2: [] };
for (const code of ANOMALY_TYPE_ORDER) {
  const meta = ANOMALY_TYPES[code];
  LAYER_TYPE_LABELS[meta.layer].push(meta.label);
}

function pct(processed: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((processed / total) * 100);
}

// ─── sub-components ─────────────────────────────────────────────────────────

function StatusGlyph({ status }: { status: LayerProgress["status"] }) {
  if (status === "done") {
    return (
      <Check
        className="size-3.5 shrink-0"
        style={{ color: "var(--status-found)" }}
      />
    );
  }
  if (status === "active") {
    return (
      <Loader2
        className="size-3.5 shrink-0 animate-spin"
        style={{ color: "var(--brand)" }}
      />
    );
  }
  return <Circle className="size-3.5 shrink-0 text-muted-foreground/40" />;
}

function CurrentType({ layer: l }: { layer: LayerProgress }) {
  if (l.status !== "active") return null;

  // L1/L2: 유형 코드 + 한글명 + 문항. L0: 코드 일괄(유형 단위가 없음) + 문항.
  let text: string;
  if (l.layer === 0) {
    text = l.currentQ ? `문항 ${l.currentQ} · 코드 일괄` : "코드 일괄";
  } else if (l.currentType) {
    const m = typeMeta(l.currentType);
    text = `${m.code} ${m.label}${l.currentQ ? ` · 문항 ${l.currentQ}` : ""}`;
  } else {
    return null;
  }

  return (
    <span
      className="truncate rounded px-1.5 py-0.5 text-[10px] font-medium tabular-nums"
      style={{
        color: "var(--brand)",
        backgroundColor: "color-mix(in oklab, var(--brand) 14%, transparent)",
      }}
      title={text}
    >
      {text}
    </span>
  );
}

function LayerRow({ layer: l }: { layer: LayerProgress }) {
  const value = pct(l.processed, l.totalQ);
  const isPending = l.status === "pending";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <LayerBadge layer={l.layer} />
        <span
          className={
            isPending
              ? "text-[12px] text-muted-foreground/60"
              : "text-[12px] text-foreground"
          }
        >
          {LAYER_LABELS[l.layer]}
        </span>
        <StatusGlyph status={l.status} />
        <CurrentType layer={l} />
        <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {l.processed}/{l.totalQ}
          {l.found > 0 && (
            <span
              className="ml-1"
              style={{ color: "var(--status-found)" }}
            >
              +{l.found}
            </span>
          )}
        </span>
      </div>
      <Progress
        value={isPending ? 0 : value}
        className={isPending ? "opacity-30" : undefined}
        aria-label={`${LAYER_LABELS[l.layer]} 진행률 ${value}%`}
      />
      {/* 해당 레이어가 검사하는 한글 유형명 (constants 파생) */}
      <p className="text-[10px] leading-relaxed text-muted-foreground/80">
        {LAYER_TYPE_LABELS[l.layer].join(" · ")}
      </p>
    </div>
  );
}

function QuestionCell({
  status,
  qNumber,
}: {
  status: "pending" | "active" | "done";
  qNumber: number;
}) {
  const base =
    "grid h-5 min-w-6 shrink-0 place-items-center rounded px-1 text-[10px] font-mono font-medium tabular-nums transition-colors";

  if (status === "active") {
    return (
      <span
        className={`${base} animate-pulse`}
        style={{
          backgroundColor: "var(--brand)",
          color: "var(--primary-foreground)",
        }}
        title={`문항 ${qNumber} 진행 중`}
      >
        {qNumber}
      </span>
    );
  }
  if (status === "done") {
    return (
      <span
        className={base}
        style={{
          backgroundColor:
            "color-mix(in oklab, var(--status-found) 18%, transparent)",
          color: "var(--status-found)",
        }}
        title={`문항 ${qNumber} 완료`}
      >
        {qNumber}
      </span>
    );
  }
  // pending
  return (
    <span
      className={`${base} bg-secondary text-muted-foreground/70`}
      title={`문항 ${qNumber} 대기`}
    >
      {qNumber}
    </span>
  );
}

// ─── main component ──────────────────────────────────────────────────────────

export function PipelineProgress({
  state,
}: {
  state: ProgressState;
}): React.JSX.Element {
  const isDone = state.phase === "done";
  const isError = state.phase === "error";

  return (
    <div className="flex flex-col gap-4 p-4 rounded-md bg-card border border-border">
      {/* ── Header ── */}
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-medium text-foreground">
          분석 진행
        </span>

        {isDone && (
          <span
            className="flex items-center gap-1 text-[12px] font-medium"
            style={{ color: "var(--status-found)" }}
          >
            <Check className="size-3.5" />
            완료
          </span>
        )}

        {isError && state.error && (
          <span
            className="text-[12px]"
            style={{ color: "var(--status-error)" }}
          >
            {state.error}
          </span>
        )}

        <div className="ml-auto flex items-center gap-3">
          <PipelineGuideLink size="xs" />
          <span className="font-mono text-[12px] text-muted-foreground tabular-nums">
            {state.elapsedSeconds}s
          </span>
          <span
            className="font-mono text-[12px] font-medium tabular-nums"
            style={{ color: "var(--status-found)" }}
          >
            탐지 {state.foundCount}
          </span>
          {(state.filteredCount > 0 ||
            state.phase === "postprocess" ||
            state.phase === "done") && (
            <span
              className="font-mono text-[12px] font-medium tabular-nums"
              style={{ color: "var(--status-filtered)" }}
              title="후처리 필터로 제거된 오탐 건수"
            >
              오탐 {state.filteredCount}
            </span>
          )}
        </div>
      </div>

      {/* ── Layer rows ── */}
      <div className="flex flex-col gap-3">
        {state.layers.map((l) => (
          <LayerRow key={l.layer} layer={l} />
        ))}
      </div>

      {/* ── Question dots ── */}
      {state.totalQ > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] text-muted-foreground">문항별 진행</span>
          <div
            className="grid gap-1"
            style={{
              // 한 줄에 최대 20개, 21번째부터 다음 줄로 (문항 수가 적으면 그 수만큼).
              gridTemplateColumns: `repeat(${Math.min(20, state.totalQ)}, minmax(0, 1fr))`,
            }}
          >
            {Array.from({ length: state.totalQ }, (_, i) => i + 1).map(
              (qNumber) => {
                const status = state.questionStatus[qNumber] ?? "pending";
                return (
                  <QuestionCell
                    key={qNumber}
                    status={status}
                    qNumber={qNumber}
                  />
                );
              }
            )}
          </div>
        </div>
      )}
    </div>
  );
}
