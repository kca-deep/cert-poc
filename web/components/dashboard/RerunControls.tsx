"use client";

/**
 * 재실행(분석 시작) 컨트롤 — 서버/LLM 미연결로 분석이 실패했거나 이미 완료된
 * 세션을, 업로드 없이 다시 분석한다. 공급자 토글을 함께 노출해 로컬 LLM 이
 * 닿지 않을 때 Claude Haiku 로 바꿔 재시도할 수 있다.
 *
 *   - RerunButton : 헤더용 컴팩트 버튼 (완료 세션 등).
 *   - RerunPanel  : 오류/연결 끊김 상태용 큰 패널 (사유 + 토글 + 버튼).
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCw, TriangleAlert, WifiOff } from "lucide-react";
import { toast } from "sonner";

import { queryKeys, rerunAnalysis } from "@/lib/api";
import { useProviderStore } from "@/lib/stores/provider";
import { Button } from "@/components/ui/button";
import {
  LlmProviderToggle,
  providerLabel,
} from "@/components/layout/LlmProviderToggle";

function useRerun(sessionId: string) {
  const queryClient = useQueryClient();
  const provider = useProviderStore((s) => s.provider);

  const mutation = useMutation({
    mutationFn: () => rerunAnalysis(sessionId, provider),
    onSuccess: () => {
      toast.success(`${providerLabel(provider)}(으)로 재실행을 시작했습니다.`);
      queryClient.invalidateQueries({ queryKey: queryKeys.session(sessionId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
    onError: () =>
      toast.error("재실행에 실패했습니다. 서버 연결을 확인해 주세요."),
  });

  return mutation;
}

export function RerunButton({ sessionId }: { sessionId: string }) {
  const { mutate, isPending } = useRerun(sessionId);
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => mutate()}
      disabled={isPending}
    >
      <RotateCw className={isPending ? "size-3.5 animate-spin" : "size-3.5"} />
      {isPending ? "재실행 중…" : "재실행"}
    </Button>
  );
}

/**
 * 오류 또는 서버 연결 끊김 상태에서 보여주는 복구 패널.
 * variant="error"        : 분석이 오류로 종료됨 (LLM 서버 미가용 등)
 * variant="disconnected" : 세션 자체를 불러오지 못함 (API 미연결)
 */
export function RerunPanel({
  sessionId,
  variant,
  message,
  onRetryFetch,
}: {
  sessionId: string;
  variant: "error" | "disconnected";
  message?: string;
  onRetryFetch?: () => void;
}) {
  const { mutate, isPending } = useRerun(sessionId);
  const [retrying, setRetrying] = useState(false);

  const disconnected = variant === "disconnected";
  const Icon = disconnected ? WifiOff : TriangleAlert;
  const title = disconnected
    ? "서버에 연결할 수 없습니다"
    : "분석이 오류로 종료되었습니다";
  const hint = disconnected
    ? "백엔드(API) 서버가 실행 중인지 확인한 뒤 다시 시도하세요. 연결이 복구되면 공급자를 바꿔 재실행할 수 있습니다."
    : "로컬 LLM 서버에 연결하지 못했을 가능성이 큽니다. 공급자를 Claude Haiku 로 바꿔 재실행하거나, 로컬 서버를 켠 뒤 재실행하세요.";

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 rounded-xl border border-border bg-card p-8 text-center">
      <span
        className="grid size-11 place-items-center rounded-full"
        style={{
          backgroundColor:
            "color-mix(in oklab, var(--status-error) 14%, transparent)",
        }}
      >
        <Icon className="size-5 text-[var(--status-error)]" />
      </span>

      <div className="space-y-1.5">
        <h2 className="text-[15px] font-medium text-foreground">{title}</h2>
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          {message ?? hint}
        </p>
      </div>

      <div className="flex flex-col items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          LLM 공급자
        </span>
        <LlmProviderToggle size="sm" />
      </div>

      <div className="flex items-center gap-2 pt-1">
        {disconnected && onRetryFetch && (
          <Button
            variant="ghost"
            size="sm"
            disabled={retrying}
            onClick={() => {
              setRetrying(true);
              onRetryFetch();
              setTimeout(() => setRetrying(false), 800);
            }}
          >
            <RotateCw className={retrying ? "size-3.5 animate-spin" : "size-3.5"} />
            연결 다시 시도
          </Button>
        )}
        <Button size="sm" onClick={() => mutate()} disabled={isPending}>
          <RotateCw className={isPending ? "size-3.5 animate-spin" : "size-3.5"} />
          {isPending ? "재실행 중…" : "분석 재실행"}
        </Button>
      </div>
    </div>
  );
}
