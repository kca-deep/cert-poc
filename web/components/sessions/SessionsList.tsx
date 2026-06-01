"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { ChevronRight, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { deleteSession, listSessions, queryKeys } from "@/lib/api";
import { STATUS_META } from "@/lib/constants";
import type { Session } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ENTER, staggerDelay } from "@/lib/anim";

const TONE_STYLE: Record<string, string> = {
  done: "text-[var(--status-found)] bg-[color-mix(in_oklab,var(--status-found)_14%,transparent)]",
  active:
    "text-[var(--layer-2)] bg-[color-mix(in_oklab,var(--layer-2)_16%,transparent)]",
  error:
    "text-[var(--status-error)] bg-[color-mix(in_oklab,var(--status-error)_14%,transparent)]",
  neutral: "text-muted-foreground bg-secondary",
};

export function SessionsList() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.sessions,
    queryFn: listSessions,
  });

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <header className={cn(ENTER, "mb-6 flex items-end justify-between")}>
        <div>
          <h1 className="text-2xl font-medium tracking-tight text-foreground">
            세션
          </h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            업로드한 문제지의 분석 결과를 확인합니다.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/upload">
            <Plus className="size-3.5" />새 분석
          </Link>
        </Button>
      </header>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : !data || data.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="flex flex-col gap-2">
          {data.map((s, i) => (
            <li key={s.id} className={cn(ENTER)} style={staggerDelay(i)}>
              <SessionRow session={s} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SessionRow({ session }: { session: Session }) {
  const status = STATUS_META[session.status];
  return (
    <div className="group flex items-center rounded-lg border border-border bg-card pr-2 transition-all hover:border-muted-foreground/40 hover:bg-card/80">
      <Link
        href={`/sessions/${session.id}`}
        className="flex min-w-0 flex-1 items-center gap-4 px-4 py-3"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
          <span className="truncate text-[14px] font-medium text-foreground">
            {session.originalFilename}
          </span>
          <span
            className={cn(
              "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium",
              TONE_STYLE[status.tone]
            )}
          >
            {status.tone === "active" && (
              <span className="mr-1 inline-block size-1.5 animate-pulse rounded-full bg-current align-middle" />
            )}
            {status.label}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
          <span className="uppercase">{session.fileType}</span>
          <span>·</span>
          <span>문항 {session.questionCount}</span>
          <span>·</span>
          <span>
            {formatDistanceToNow(new Date(session.createdAt), {
              addSuffix: true,
              locale: ko,
            })}
          </span>
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end">
        <span className="font-mono text-lg leading-none tabular-nums text-foreground">
          <span
            className={
              session.foundCount > 0
                ? "text-[var(--status-found)]"
                : "text-muted-foreground"
            }
          >
            {session.foundCount}
          </span>
        </span>
        <span className="mt-0.5 text-[10px] text-muted-foreground">탐지</span>
      </div>

        <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </Link>

      <DeleteSessionButton session={session} />
    </div>
  );
}

function DeleteSessionButton({ session }: { session: Session }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const isRunning = session.status === "running";

  const { mutate, isPending } = useMutation({
    mutationFn: () => deleteSession(session.id),
    onSuccess: () => {
      toast.success("세션이 삭제되었습니다.");
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      setOpen(false);
    },
    onError: () =>
      toast.error("삭제에 실패했습니다. 서버 연결을 확인해 주세요."),
  });

  // 진행 중(running) 세션은 백그라운드 파이프라인이 아직 쓰는 중이라 삭제를 막는다.
  if (isRunning) {
    return (
      <Button
        variant="ghost"
        size="icon-sm"
        disabled
        aria-label="진행 중인 세션은 삭제할 수 없습니다"
        title="진행 중인 세션은 삭제할 수 없습니다"
      >
        <Trash2 className="size-3.5" />
      </Button>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="세션 삭제">
          <Trash2 className="size-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>세션을 삭제할까요?</DialogTitle>
          <DialogDescription>
            <span className="font-medium text-foreground">
              {session.originalFilename}
            </span>
            의 분석·검수 결과가 모두 삭제되며 되돌릴 수 없습니다.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm">
              취소
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => mutate()}
            disabled={isPending}
          >
            {isPending ? "삭제 중…" : "삭제"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EmptyState() {
  return (
    <div className="grid place-items-center rounded-lg border border-dashed border-border bg-muted/30 py-20 text-center">
      <p className="text-[13px] text-muted-foreground">
        아직 분석 세션이 없습니다. 왼쪽{" "}
        <span className="font-medium text-foreground">＋ 새 분석</span>으로
        시작하세요.
      </p>
    </div>
  );
}
