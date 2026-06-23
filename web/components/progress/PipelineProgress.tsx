"use client";

/**
 * PipelineProgress — holistic 문항단위 분석 진행 시각화.
 * 순수 표현 컴포넌트: ProgressState 를 받아 렌더만 한다(타이머/시뮬레이션 없음).
 * "분석 중" 세션 뷰에서 사용. 레이어 개념 없이 문항당 LLM 1콜(holistic) 진행을 보여준다.
 */

import type { ProgressState, QuestionDotStatus } from "@/lib/sse";
import { agentMeta } from "@/lib/constants";
import { Progress } from "@/components/ui/progress";
import { PipelineGuideLink } from "@/components/pipeline/PipelineGuideLink";
import { Check } from "lucide-react";

// ─── helpers ────────────────────────────────────────────────────────────────

function pct(processed: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((processed / total) * 100);
}

// 경과 초를 mm:ss 로 표기(1시간 초과 시 h:mm:ss).
function fmtElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return hh > 0 ? `${hh}:${pad(mm)}:${pad(ss)}` : `${pad(mm)}:${pad(ss)}`;
}

// ─── sub-components ─────────────────────────────────────────────────────────

function QuestionCell({
  status,
  qNumber,
  hasFindings,
  selected,
  onSelect,
  agentColor,
  agentLabel,
}: {
  status: QuestionDotStatus;
  qNumber: number;
  hasFindings: boolean;
  selected: boolean;
  onSelect?: (q: number) => void;
  agentColor?: string;
  agentLabel?: string;
}) {
  const base =
    "grid h-7 min-w-8 shrink-0 place-items-center rounded px-1.5 text-[13px] font-mono font-medium tabular-nums transition-all";

  let bg = "var(--secondary)";
  let fg = "var(--muted-foreground)";
  let title = `문항 ${qNumber} 대기`;
  let pulse = "";
  let glyph: string | number = qNumber;
  if (status === "active") {
    // 처리 중인 문항은 담당 에이전트 색으로 (어느 agent 가 도는지 그리드에서 바로 보임).
    // agent 색(amber/blue/violet)은 모두 중간 명도라 흰글씨는 대비 부족 → 어두운 글씨.
    bg = agentColor ?? "var(--brand)";
    fg = "#171717";
    title = agentLabel
      ? `문항 ${qNumber} — ${agentLabel} 검토 중`
      : `문항 ${qNumber} 검토 중`;
    pulse = "animate-pulse";
  } else if (status === "error") {
    // 검토 실패(타임아웃/파싱오류) — 무오류 완료와 구분되는 주황 + ! 표시.
    bg = "#f59e0b";
    fg = "#1c1c1c";
    glyph = "!";
    title = `문항 ${qNumber} — 검토 실패(재시도 필요)`;
  } else if (status === "done" && hasFindings) {
    // 오류가 발견된 문항 — 빨강 톤으로 강조(클릭해 내용 확인).
    bg = "color-mix(in oklab, var(--status-error) 24%, transparent)";
    fg = "var(--status-error)";
    title = `문항 ${qNumber} — 오류 발견 (클릭해 내용 보기)`;
  } else if (status === "done") {
    bg = "color-mix(in oklab, var(--status-found) 18%, transparent)";
    fg = "var(--status-found)";
    title = `문항 ${qNumber} 완료 (오류 없음)`;
  }
  const cls = [
    base,
    pulse,
    selected ? "ring-2 ring-[var(--brand)]" : "",
    onSelect ? "cursor-pointer hover:scale-110" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const style = { backgroundColor: bg, color: fg };

  if (onSelect) {
    return (
      <button
        type="button"
        onClick={() => onSelect(qNumber)}
        className={cls}
        style={style}
        title={title}
      >
        {glyph}
      </button>
    );
  }
  return (
    <span className={cls} style={style} title={title}>
      {glyph}
    </span>
  );
}

// ─── main component ──────────────────────────────────────────────────────────

const PHASE_LABEL: Record<ProgressState["phase"], string> = {
  starting: "분석 준비 중",
  running: "검토 진행 중",
  done: "완료",
  error: "오류",
};

export function PipelineProgress({
  state,
  selectedQ = null,
  onSelectQ,
}: {
  state: ProgressState;
  selectedQ?: number | null;
  onSelectQ?: (q: number) => void;
}): React.JSX.Element {
  const isDone = state.phase === "done";
  const isError = state.phase === "error";
  const value = pct(state.processed, state.totalQ);

  // 논리 레인 → 현재 처리 중 문항 (agentA/B/C 스트립용).
  const byLane: Record<number, number> = {};
  for (const [qStr, lane] of Object.entries(state.workerByQ)) {
    byLane[lane] = Number(qStr);
  }
  const activeLanes = Object.keys(byLane)
    .map(Number)
    .sort((a, b) => a - b);

  return (
    <div className="flex flex-col gap-4 p-4 rounded-md bg-card border border-border">
      {/* ── Header ── */}
      <div className="flex items-center gap-2">
        <span className="text-[16px] font-semibold text-foreground">
          분석 진행
        </span>

        {isDone ? (
          <span
            className="flex items-center gap-1 text-[13px] font-medium"
            style={{ color: "var(--status-found)" }}
          >
            <Check className="size-3.5" />
            완료
          </span>
        ) : isError && state.error ? (
          <span className="text-[13px]" style={{ color: "var(--status-error)" }}>
            {state.error}
          </span>
        ) : (
          <span className="text-[13px] text-muted-foreground">
            {PHASE_LABEL[state.phase]}
          </span>
        )}

        <div className="ml-auto flex items-center gap-3">
          <PipelineGuideLink size="xs" />
          <span className="font-mono text-[13px] text-muted-foreground tabular-nums">
            {fmtElapsed(state.elapsedSeconds)}
          </span>
          <span
            className="font-mono text-[13px] font-medium tabular-nums"
            style={{ color: "var(--status-found)" }}
            title="누적 탐지 오류 건수"
          >
            탐지 {state.foundCount}
          </span>
          {state.errorQ > 0 && (
            <span
              className="font-mono text-[13px] font-medium tabular-nums"
              style={{ color: "var(--status-error)" }}
              title="오류가 1건 이상인 문항 수"
            >
              오류문항 {state.errorQ}
            </span>
          )}
          {state.erroredQ > 0 && (
            <span
              className="font-mono text-[13px] font-medium tabular-nums"
              style={{ color: "#f59e0b" }}
              title="검토 실패(타임아웃/파싱오류) 문항 수 — 재실행 권장"
            >
              검토실패 {state.erroredQ}
            </span>
          )}
        </div>
      </div>

      {/* ── Overall progress (문항 단위) ── */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-[13px]">
          <span className="text-muted-foreground">
            holistic 검출 — 문항당 LLM 1콜
          </span>
          <span className="font-mono text-muted-foreground tabular-nums">
            {state.processed}/{state.totalQ}
          </span>
        </div>
        <Progress value={value} aria-label={`분석 진행률 ${value}%`} />
      </div>

      {/* ── 현재 처리 중 (병렬 에이전트) ── */}
      {state.phase === "running" && activeLanes.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] text-muted-foreground">
            현재 처리 중 — 동시 {activeLanes.length}문항(병렬)
          </span>
          <div className="flex flex-wrap gap-1.5">
            {activeLanes.map((lane) => {
              const m = agentMeta(lane);
              const q = byLane[lane];
              return (
                <span
                  key={lane}
                  className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] font-medium"
                  style={{
                    color: m.color,
                    backgroundColor: `color-mix(in oklab, ${m.color} 14%, transparent)`,
                  }}
                >
                  <span
                    className="size-1.5 rounded-full animate-pulse"
                    style={{ backgroundColor: m.color }}
                  />
                  {m.label}
                  <span className="font-mono tabular-nums text-muted-foreground">
                    문항 {String(q).padStart(2, "0")}
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Question dots ── */}
      {state.totalQ > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] text-muted-foreground">
            문항별 진행{onSelectQ ? " — 빨간 문항을 클릭하면 탐지 내용이 보입니다" : ""}
          </span>
          <div
            className="grid gap-1.5"
            style={{
              // 한 줄에 10개씩(10단위로 끊어 표시) — 11번째부터 다음 줄.
              gridTemplateColumns: `repeat(${Math.min(10, state.totalQ)}, minmax(0, 1fr))`,
            }}
          >
            {Array.from({ length: state.totalQ }, (_, i) => i + 1).map(
              (qNumber) => {
                const status = state.questionStatus[qNumber] ?? "pending";
                const hasFindings =
                  (state.findingsByQ[qNumber]?.length ?? 0) > 0;
                const lane = state.workerByQ[qNumber];
                const agent = lane != null ? agentMeta(lane) : undefined;
                return (
                  <QuestionCell
                    key={qNumber}
                    status={status}
                    qNumber={qNumber}
                    hasFindings={hasFindings}
                    selected={selectedQ === qNumber}
                    onSelect={onSelectQ}
                    agentColor={agent?.color}
                    agentLabel={agent?.label}
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
