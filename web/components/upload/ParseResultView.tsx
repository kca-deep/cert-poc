"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Info,
  RotateCcw,
  Sparkles,
} from "lucide-react";

import type { ParseResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  LlmProviderToggle,
  useLlmProvider,
} from "@/components/layout/LlmProviderToggle";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function ParseResultView({
  result,
  onStart,
  onReset,
  starting,
}: {
  result: ParseResult;
  onStart: () => void;
  onReset: () => void;
  starting?: boolean;
}) {
  const [tab, setTab] = useState("preview");
  const warnCount = result.warnings.filter(
    (w) => w.severity === "warning"
  ).length;
  const { claudeAvailable, configLoaded, localAvailable } = useLlmProvider();
  const hasAvailableProvider = claudeAvailable || localAvailable;
  const canStart =
    configLoaded && hasAvailableProvider && result.questionCount > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {/* parse summary */}
      <div className="shrink-0 rounded-lg border border-border bg-card">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-3">
          <CheckCircle2 className="size-4 text-[var(--status-found)]" />
          <span className="text-[14px] font-medium text-foreground">
            파싱 완료
          </span>
          <span className="truncate font-mono text-[12px] text-muted-foreground">
            {result.filename}
          </span>
        </div>
        <div className="grid grid-cols-3 divide-x divide-border">
          <Stat label="형식" value={result.fileType.toUpperCase()} />
          <Stat label="추출 문항" value={String(result.questionCount)} accent />
          <Stat label="용량" value={formatSize(result.sizeBytes)} />
        </div>
      </div>

      {/* warnings — pre-analysis sanity checks */}
      {result.warnings.length > 0 && (
        <div className="shrink-0 rounded-lg border border-border bg-card px-4 py-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[12px] font-medium text-foreground">
              파싱 점검
            </span>
            {warnCount > 0 && (
              <span
                className="rounded px-1.5 py-0.5 font-mono text-[10px] font-medium"
                style={{
                  color: "var(--status-filtered)",
                  backgroundColor:
                    "color-mix(in oklab, var(--status-filtered) 16%, transparent)",
                }}
              >
                주의 {warnCount}
              </span>
            )}
          </div>
          <ul className="flex flex-col gap-1.5">
            {result.warnings.map((w, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px]">
                {w.severity === "warning" ? (
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-[var(--status-filtered)]" />
                ) : (
                  <Info className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                )}
                <span className="text-muted-foreground">
                  {w.qNumber != null && (
                    <span className="mr-1 font-mono text-foreground">
                      문항 {w.qNumber}
                    </span>
                  )}
                  {w.message}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* parsed markdown preview — fills remaining height, scrolls internally */}
      <Tabs
        value={tab}
        onValueChange={setTab}
        className="flex min-h-0 flex-1 flex-col gap-2"
      >
        <TabsList className="shrink-0">
          <TabsTrigger value="preview">
            <FileText className="size-3.5" />
            문항 미리보기
          </TabsTrigger>
          <TabsTrigger value="raw">원본 마크다운</TabsTrigger>
        </TabsList>

        <TabsContent value="preview" className="min-h-0 flex-1">
          <ScrollArea className="h-full rounded-lg border border-border bg-card">
            <ul className="divide-y divide-border">
              {result.questions.map((q, i) => (
                <li key={`${q.qNumber}-${i}`} className="px-4 py-3">
                  <div className="mb-1 font-mono text-[11px] tabular-nums text-muted-foreground">
                    문항 {String(q.qNumber).padStart(2, "0")}
                  </div>
                  <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-foreground">
                    {q.mdText.replace(/^##\s*\d+\.\s*/, "")}
                  </pre>
                </li>
              ))}
            </ul>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="raw" className="min-h-0 flex-1">
          <ScrollArea className="h-full rounded-lg border border-border bg-[#141414]">
            <pre className="whitespace-pre-wrap p-4 font-mono text-[12px] leading-relaxed text-foreground/90">
              {result.mergedMd}
            </pre>
          </ScrollArea>
        </TabsContent>
      </Tabs>

      {/* actions — the single filled emerald CTA on this screen */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <Button variant="ghost" size="sm" onClick={onReset} disabled={starting}>
          <RotateCcw className="size-3.5" />
          다른 파일
        </Button>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">공급자</span>
            <LlmProviderToggle size="sm" />
          </div>
          <Button
          size="lg"
          onClick={onStart}
          disabled={starting || !canStart}
          className={cn(starting && "opacity-80")}
        >
            <Sparkles className="size-4" />
            {starting
              ? "분석 시작 중…"
              : !configLoaded
                ? "LLM 상태 확인 중…"
                : hasAvailableProvider
                ? "윤문 분석 시작"
                : "LLM 연결 필요"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 font-mono text-lg tabular-nums",
          accent ? "text-[var(--status-found)]" : "text-foreground"
        )}
      >
        {value}
      </div>
    </div>
  );
}
