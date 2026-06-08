"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { parseUpload, queryKeys, startAnalysis } from "@/lib/api";
import { ENTER, staggerDelay } from "@/lib/anim";
import type { ParseResult } from "@/lib/types";
import { useProviderStore } from "@/lib/stores/provider";
import { cn } from "@/lib/utils";

import { FileDropzone } from "./FileDropzone";
import { ParseResultView } from "./ParseResultView";
import { PipelineGuideLink } from "@/components/pipeline/PipelineGuideLink";

type Stage = "idle" | "parsing" | "parsed" | "starting" | "error";

export function UploadView() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const provider = useProviderStore((s) => s.provider);

  const [stage, setStage] = useState<Stage>("idle");
  const [result, setResult] = useState<ParseResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [parsingName, setParsingName] = useState<string>("");

  const handleFile = async (file: File) => {
    setStage("parsing");
    setParsingName(file.name);
    setErrorMsg(null);
    try {
      const parsed = await parseUpload(file);
      setResult(parsed);
      setStage("parsed");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "파싱에 실패했습니다.");
      setStage("error");
    }
  };

  const handleStart = async () => {
    if (!result) return;
    setStage("starting");
    try {
      const id = await startAnalysis(result, provider);
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      toast.success("윤문 분석을 시작했습니다.");
      router.push(`/sessions/${id}`);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "분석 시작에 실패했습니다.");
      setStage("error");
    }
  };

  const reset = () => {
    setStage("idle");
    setResult(null);
    setErrorMsg(null);
  };

  const showResult = (stage === "parsed" || stage === "starting") && result;

  return (
    // 뷰포트 높이를 채우고, 내부에서만 스크롤이 일어나도록 한다 (이중 스크롤 방지).
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-8">
      <header
        className={cn("mb-5 shrink-0 text-center", ENTER)}
        style={staggerDelay(0)}
      >
        <h1 className="text-2xl font-medium tracking-tight text-foreground">
          새 분석
        </h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          시험지를 업로드하면 마크다운으로 파싱하고, 확인 후 윤문 분석을
          시작합니다.
        </p>
        <div className="mt-2 flex justify-center">
          <PipelineGuideLink size="xs" />
        </div>
      </header>

      {/* step indicator */}
      <div className={cn("shrink-0", ENTER)} style={staggerDelay(1)}>
        <Steps stage={stage} />
      </div>

      <div
        className={cn("mt-5 flex min-h-0 flex-1 flex-col", ENTER)}
        style={staggerDelay(2)}
      >
        {(stage === "idle" || stage === "error") && (
          <div className="flex flex-1 flex-col justify-center">
            <FileDropzone onFile={handleFile} />
            {stage === "error" && errorMsg && (
              <p className="mt-3 text-center text-[12px] text-[var(--status-error)]">
                {errorMsg}
              </p>
            )}
          </div>
        )}

        {stage === "parsing" && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-border bg-card text-center">
            <Loader2 className="size-6 animate-spin text-brand" />
            <p className="text-[13px] text-foreground">마크다운으로 파싱 중…</p>
            <p className="font-mono text-[11px] text-muted-foreground">
              {parsingName}
            </p>
          </div>
        )}

        {showResult && (
          <ParseResultView
            result={result}
            onStart={handleStart}
            onReset={reset}
            starting={stage === "starting"}
          />
        )}
      </div>
    </div>
  );
}

function Steps({ stage }: { stage: Stage }) {
  const current =
    stage === "idle" || stage === "error"
      ? 0
      : stage === "parsing"
        ? 1
        : 2; // parsed / starting

  const steps = ["업로드", "파싱 확인", "분석 시작"];
  return (
    <ol className="flex items-center justify-center gap-2 text-[12px]">
      {steps.map((label, i) => {
        const active = i === current;
        const done = i < current;
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className="grid size-5 place-items-center rounded-full font-mono text-[10px] tabular-nums"
              style={{
                backgroundColor: done
                  ? "var(--status-found)"
                  : active
                    ? "color-mix(in oklab, var(--brand) 18%, transparent)"
                    : "var(--secondary)",
                color: done
                  ? "var(--primary-foreground)"
                  : active
                    ? "var(--brand)"
                    : "var(--muted-foreground)",
              }}
            >
              {i + 1}
            </span>
            <span
              className={
                active
                  ? "font-medium text-foreground"
                  : "text-muted-foreground"
              }
            >
              {label}
            </span>
            {i < steps.length - 1 && (
              <span className="mx-1 h-px w-6 bg-border" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
