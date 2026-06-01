"use client";

import { useMemo, useState } from "react";

import type { AnomalyResult, Question } from "@/lib/types";
import { LAYER_META } from "@/lib/constants";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

type Filter = "all" | "found";

export function QuestionList({
  questions,
  results,
  selectedQ,
  onSelect,
}: {
  questions: Question[];
  results: AnomalyResult[];
  selectedQ: number | null;
  onSelect: (q: number) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");

  const byQ = useMemo(() => {
    const map = new Map<number, AnomalyResult[]>();
    for (const r of results) {
      if (!r.found) continue;
      const arr = map.get(r.qNumber) ?? [];
      arr.push(r);
      map.set(r.qNumber, arr);
    }
    return map;
  }, [results]);

  const shown = questions.filter((q) =>
    filter === "found" ? byQ.has(q.qNumber) : true
  );
  const foundTotal = byQ.size;

  return (
    <div className="flex h-full flex-col">
      {/* segmented filter */}
      <div className="flex items-center gap-1 border-b border-border px-2 py-2">
        <FilterChip
          active={filter === "all"}
          onClick={() => setFilter("all")}
          label="전체"
          count={questions.length}
        />
        <FilterChip
          active={filter === "found"}
          onClick={() => setFilter("found")}
          label="탐지"
          count={foundTotal}
          accent
        />
      </div>

      <ScrollArea className="flex-1">
        <ul className="flex flex-col p-1.5">
          {shown.map((q) => {
            const qResults = byQ.get(q.qNumber) ?? [];
            const active = selectedQ === q.qNumber;
            // 윤문 탐지 건수가 많을수록 문항 배경을 더 짙은 에메랄드로 표시.
            const tint = rowTint(qResults.length);
            return (
              <li key={q.qNumber}>
                <button
                  type="button"
                  onClick={() => onSelect(q.qNumber)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                    active
                      ? "text-foreground ring-1 ring-inset ring-[var(--brand)]/50"
                      : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                  )}
                  style={{ backgroundColor: tint }}
                >
                  <span className="w-7 shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                    {String(q.qNumber).padStart(2, "0")}
                  </span>
                  <span className="flex-1 truncate text-[13px]">
                    {questionPreview(q.mdText)}
                  </span>
                  {qResults.length > 0 && (
                    <span className="flex shrink-0 items-center gap-0.5">
                      {qResults.slice(0, 4).map((r, i) => (
                        <span
                          key={i}
                          className="size-1.5 rounded-full"
                          style={{
                            backgroundColor: r.filtered
                              ? "var(--status-filtered)"
                              : `var(${LAYER_META[r.layer].varName})`,
                          }}
                        />
                      ))}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
          {shown.length === 0 && (
            <li className="px-3 py-6 text-center text-[12px] text-muted-foreground">
              탐지된 문항이 없습니다.
            </li>
          )}
        </ul>
      </ScrollArea>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  count,
  accent,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  accent?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] font-medium transition-colors",
        active
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      {label}
      <span
        className={cn(
          "font-mono text-[11px] tabular-nums",
          accent && count > 0 ? "text-[var(--status-found)]" : "text-muted-foreground"
        )}
      >
        {count}
      </span>
    </button>
  );
}

// 문항 행 배경 틴트: 윤문 탐지 건수가 많을수록 짙은 에메랄드 (매트릭스와 동일 스케일).
function rowTint(n: number): string | undefined {
  if (n <= 0) return undefined;
  const pct = n === 1 ? 12 : n === 2 ? 22 : n === 3 ? 32 : n === 4 ? 42 : 52;
  return `color-mix(in oklab, var(--status-found) ${pct}%, transparent)`;
}

function questionPreview(md: string): string {
  const body = md.replace(/^##\s*\d+\.\s*/, "");
  for (const line of body.split("\n")) {
    const clean = line.replace(/[#>*`]/g, "").trim();
    if (clean) return clean;
  }
  return "";
}
