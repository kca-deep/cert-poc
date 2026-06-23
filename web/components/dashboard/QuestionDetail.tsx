"use client";

import { FileText } from "lucide-react";

import type { Finding, Question } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";

import { AnomalyCard } from "./AnomalyCard";

export function QuestionDetail({
  sessionId,
  question,
  findings,
}: {
  sessionId: string;
  question: Question | null;
  findings: Finding[];
}) {
  if (!question) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted-foreground">
        <FileText className="size-5 opacity-50" />
        <p className="text-[13px]">왼쪽에서 문항을 선택하세요.</p>
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 p-4">
        {/* original question text */}
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="font-mono text-xs tabular-nums text-muted-foreground">
              문항 {String(question.qNumber).padStart(2, "0")}
            </span>
            <span className="h-px flex-1 bg-border" />
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
              탐지 {findings.length}
            </span>
          </div>
          <div className="rounded-md border border-border bg-secondary/30 p-3">
            <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-foreground">
              {question.mdText}
            </pre>
          </div>
        </div>

        {/* detections */}
        {findings.length > 0 ? (
          <div className="flex flex-col gap-2">
            {findings.map((f) => (
              <AnomalyCard key={f.id} sessionId={sessionId} finding={f} />
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-border py-8 text-center text-[12px] text-muted-foreground">
            이 문항에서 탐지된 오류가 없습니다.
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
