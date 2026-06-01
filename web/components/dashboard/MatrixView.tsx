"use client";

import { useMemo } from "react";

import { ANOMALY_TYPE_ORDER, typeMeta } from "@/lib/constants";
import type { AnomalyResult, Question } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export function MatrixView({
  questions,
  results,
  onSelectQ,
}: {
  questions: Question[];
  results: AnomalyResult[];
  onSelectQ: (q: number) => void;
}) {
  // 담당자 화면은 실제 탐지(found)만 노출한다. 오탐(filtered)은 검수자가 확인할
  // 대상이 아니라 개발 단계에서 제거할 사안이므로 매트릭스에 표시하지 않는다.
  const cols = useMemo(() => {
    const present = new Set(results.filter((r) => r.found).map((r) => r.typeCode));
    return ANOMALY_TYPE_ORDER.filter((c) => present.has(c));
  }, [results]);

  const cell = useMemo(() => {
    const map = new Map<string, AnomalyResult>();
    for (const r of results) {
      if (r.found) map.set(`${r.qNumber}:${r.typeCode}`, r);
    }
    return map;
  }, [results]);

  // 문항별 탐지 건수 — 행 히트맵 강도를 결정한다 (많을수록 진함).
  const foundByQ = useMemo(() => {
    const map = new Map<number, number>();
    for (const r of results) {
      if (r.found) map.set(r.qNumber, (map.get(r.qNumber) ?? 0) + 1);
    }
    return map;
  }, [results]);

  if (cols.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border py-16 text-center text-[13px] text-muted-foreground">
        탐지된 오류가 없어 매트릭스가 비어 있습니다.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border">
      <div className="flex items-center gap-3 border-b border-border px-3 py-2 text-[11px] text-muted-foreground">
        <Legend color="var(--status-found)" label="탐지" />
        <span className="inline-flex items-center gap-1.5">
          <span className="flex items-center gap-0.5">
            {[1, 2, 3, 5].map((n) => (
              <span
                key={n}
                className="size-2 rounded-full"
                style={{ backgroundColor: rowTint(n) }}
              />
            ))}
          </span>
          탐지 건수(진할수록 많음)
        </span>
      </div>
      <ScrollArea className="max-h-[60vh]">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border">
              <th className="sticky left-0 z-10 bg-card px-3 py-2 text-left font-mono font-medium text-muted-foreground">
                문항
              </th>
              {cols.map((c) => (
                <th
                  key={c}
                  className="px-1.5 py-2 text-center font-mono font-medium text-muted-foreground"
                  title={typeMeta(c).label}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {questions.map((q) => {
              const foundCount = foundByQ.get(q.qNumber) ?? 0;
              const tint = rowTint(foundCount);
              return (
                <tr
                  key={q.qNumber}
                  className="border-b border-border/50 last:border-0 hover:bg-secondary/40"
                  style={{ backgroundColor: tint }}
                >
                  <td
                    className={cn(
                      "sticky left-0 z-10 px-3 py-1.5 font-mono tabular-nums text-muted-foreground",
                      foundCount === 0 && "bg-card"
                    )}
                    style={{ backgroundColor: tint ?? "var(--card)" }}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectQ(q.qNumber)}
                      className="hover:text-foreground"
                    >
                      {String(q.qNumber).padStart(2, "0")}
                    </button>
                    {foundCount > 0 ? (
                      <span
                        className="ml-1.5 font-mono text-[10px] tabular-nums"
                        style={{ color: "var(--status-found)" }}
                        title={`탐지 ${foundCount}건`}
                      >
                        {foundCount}
                      </span>
                    ) : null}
                  </td>
                  {cols.map((c) => {
                    const r = cell.get(`${q.qNumber}:${c}`);
                    return (
                      <td key={c} className="px-1.5 py-1.5 text-center">
                        {r ? (
                          <button
                            type="button"
                            onClick={() => onSelectQ(q.qNumber)}
                            className="inline-grid place-items-center"
                            title={`${c} · ${typeMeta(c).label}`}
                          >
                            <span
                              className="size-2 rounded-full transition-transform hover:scale-150"
                              style={{ backgroundColor: "var(--status-found)" }}
                            />
                          </button>
                        ) : (
                          <span className="text-border">·</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollArea>
    </div>
  );
}

// 문항별 탐지 건수 히트맵 틴트. 건수가 많을수록 진한 emerald.
function rowTint(n: number): string | undefined {
  if (n <= 0) return undefined;
  const pct = n === 1 ? 12 : n === 2 ? 22 : n === 3 ? 32 : n === 4 ? 42 : 52;
  return `color-mix(in oklab, var(--status-found) ${pct}%, transparent)`;
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
