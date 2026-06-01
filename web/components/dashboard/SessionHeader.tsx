"use client";

import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { FileSpreadsheet, FileDown, HardDrive, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { STATUS_META } from "@/lib/constants";
import type { Session } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { RerunButton } from "./RerunControls";
import { providerLabel } from "@/components/layout/LlmProviderToggle";

const TONE_STYLE: Record<string, string> = {
  done: "text-[var(--status-found)] bg-[color-mix(in_oklab,var(--status-found)_14%,transparent)]",
  active:
    "text-[var(--layer-2)] bg-[color-mix(in_oklab,var(--layer-2)_16%,transparent)]",
  error:
    "text-[var(--status-error)] bg-[color-mix(in_oklab,var(--status-error)_14%,transparent)]",
  neutral: "text-muted-foreground bg-secondary",
};

export function SessionHeader({
  session,
  condensed = false,
}: {
  session: Session;
  condensed?: boolean;
}) {
  const status = STATUS_META[session.status];

  const stub = (what: string) => () =>
    toast.info(`${what} 내보내기는 백엔드 연결 후 제공됩니다.`);

  return (
    <header
      className={cn(
        // 불투명 배경(블러 제거): backdrop-blur 는 스크롤 시 매 프레임 재래스터→글씨 흔들림.
        // transition 도 padding 으로 한정(transition-all 은 font-size까지 애니메이션→리플로우).
        "sticky top-0 z-20 flex flex-nowrap items-center gap-x-3 border-b border-border bg-background transition-[padding] duration-150",
        condensed ? "px-5 py-2 shadow-sm" : "px-5 py-4"
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h1
            className={cn(
              // font-size 는 트랜지션하지 않음(전환 중 리플로우/깨짐 방지) — 즉시 스냅.
              "truncate font-medium tracking-tight text-foreground",
              condensed ? "text-[13px]" : "text-lg"
            )}
          >
            {session.originalFilename}
          </h1>
          <span
            className={cn(
              "shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
              TONE_STYLE[status.tone]
            )}
          >
            {status.tone === "active" && (
              <span className="mr-1 inline-block size-1.5 animate-pulse rounded-full bg-current align-middle" />
            )}
            {status.label}
          </span>
          {/* condensed: 한 줄 안에 핵심 메타(문항·탐지)만 인라인 표기 */}
          {condensed && (
            <span className="ml-1 shrink-0 font-mono text-[11px] text-muted-foreground">
              문항 {session.questionCount} · 탐지{" "}
              <span className="text-[var(--status-found)]">
                {session.foundCount}
              </span>
            </span>
          )}
        </div>
        {!condensed && (
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <span className="uppercase">{session.fileType}</span>
          <span>·</span>
          <span>문항 {session.questionCount}</span>
          <span>·</span>
          <span className="text-foreground">
            탐지{" "}
            <span className="text-[var(--status-found)]">
              {session.foundCount}
            </span>
          </span>
          {typeof session.elapsedSeconds === "number" && (
            <>
              <span>·</span>
              <span>{session.elapsedSeconds}s</span>
            </>
          )}
          <span>·</span>
          <span className="inline-flex items-center gap-1 text-foreground">
            {session.provider === "claude" ? (
              <Sparkles className="size-3 text-[var(--layer-1)]" />
            ) : (
              <HardDrive className="size-3 text-muted-foreground" />
            )}
            {providerLabel(session.provider)}
          </span>
          <span>·</span>
          <span>
            {formatDistanceToNow(new Date(session.createdAt), {
              addSuffix: true,
              locale: ko,
            })}
          </span>
        </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {(session.status === "done" || session.status === "error") && (
          <RerunButton sessionId={session.id} />
        )}
        {/* 축약 시 라벨을 숨겨 아이콘만 → 가로 공간 확보(컨텐츠 영역 확장) */}
        <Button variant="outline" size="sm" onClick={stub("Excel")}>
          <FileSpreadsheet className="size-3.5" />
          {!condensed && "Excel"}
        </Button>
        <Button variant="outline" size="sm" onClick={stub("PDF")}>
          <FileDown className="size-3.5" />
          {!condensed && "PDF"}
        </Button>
      </div>
    </header>
  );
}
