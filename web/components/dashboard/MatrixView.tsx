"use client";

import { useMemo } from "react";

import { ERROR_TYPE_ORDER, errorTypeMeta } from "@/lib/constants";
import type { ErrorType, Finding, Question } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export function MatrixView({
  questions,
  findings,
  onSelectQ,
}: {
  questions: Question[];
  findings: Finding[];
  onSelectQ: (q: number) => void;
}) {
  // 열 = 실제 탐지된 error_type 만 노출 (안정 표시순서로 정렬).
  const cols = useMemo(() => {
    const present = new Set(findings.map((f) => f.errorType));
    return ERROR_TYPE_ORDER.filter((c) => present.has(c));
  }, [findings]);

  // 셀 = (문항, error_type) → 해당 finding 존재 여부.
  const cell = useMemo(() => {
    const map = new Map<string, Finding>();
    for (const f of findings) map.set(`${f.qNumber}:${f.errorType}`, f);
    return map;
  }, [findings]);

  // 문항별 탐지 건수 — 행 히트맵 강도를 결정한다 (많을수록 진함).
  const foundByQ = useMemo(() => {
    const map = new Map<number, number>();
    for (const f of findings) {
      map.set(f.qNumber, (map.get(f.qNumber) ?? 0) + 1);
    }
    return map;
  }, [findings]);

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
        <span className="inline-flex items-center gap-1.5">
          <span className="flex items-center gap-0.5">
            {cols.slice(0, 5).map((c) => (
              <span
                key={c}
                className="size-2 rounded-full"
                style={{ backgroundColor: errorTypeMeta(c).color }}
              />
            ))}
          </span>
          오류 유형별 색
        </span>
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
                  className="px-1.5 py-2 text-center font-medium text-muted-foreground"
                  title={errorTypeMeta(c).label}
                >
                  <span className="inline-flex items-center gap-1">
                    <span
                      className="size-1.5 rounded-full"
                      style={{ backgroundColor: errorTypeMeta(c).color }}
                    />
                    {c}
                  </span>
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
                    const f = cell.get(`${q.qNumber}:${c}`);
                    return (
                      <td key={c} className="px-1.5 py-1.5 text-center">
                        {f ? (
                          <button
                            type="button"
                            onClick={() => onSelectQ(q.qNumber)}
                            className="inline-grid place-items-center"
                            title={`${c} · ${errorTypeMeta(c as ErrorType).label}`}
                          >
                            <span
                              className="size-2 rounded-full transition-transform hover:scale-150"
                              style={{ backgroundColor: errorTypeMeta(c).color }}
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
