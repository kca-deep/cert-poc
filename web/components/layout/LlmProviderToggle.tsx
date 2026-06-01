"use client";

/**
 * LlmProviderToggle — 로컬 LLM ↔ Claude Haiku 토글.
 *
 * tweakcn(라이트/다크 토글)의 "아이콘 + 부드러운 트랜지션" 컨셉을 가져와,
 * 두 공급자를 위한 세그먼트 토글로 커스터마이징했다. 슬라이딩 thumb 가
 * 활성 공급자 쪽으로 이동하고 아이콘이 크로스페이드된다.
 *
 * 선택은 useProviderStore(localStorage 영속)에 저장돼 새 분석/재실행에 쓰인다.
 * GET /config/llm 으로 기본 공급자/가용성을 1회 hydrate 하며, claude 키가
 * 없으면 claude 세그먼트를 비활성화하고 사유를 툴팁으로 안내한다.
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { HardDrive, Sparkles } from "lucide-react";

import { getLlmConfig, queryKeys } from "@/lib/api";
import { useProviderStore } from "@/lib/stores/provider";
import type { LlmProvider } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const OPTIONS: { id: LlmProvider; label: string; short: string; Icon: typeof HardDrive }[] = [
  { id: "local", label: "로컬 LLM", short: "로컬", Icon: HardDrive },
  { id: "claude", label: "Claude Haiku", short: "Haiku", Icon: Sparkles },
];

/** 토글 상태 + 서버 메타를 묶어 반환하는 공유 훅. */
export function useLlmProvider() {
  const provider = useProviderStore((s) => s.provider);
  const setProvider = useProviderStore((s) => s.setProvider);
  const hydrateDefault = useProviderStore((s) => s.hydrateDefault);

  const { data: config } = useQuery({
    queryKey: queryKeys.llmConfig,
    queryFn: getLlmConfig,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (config?.default) hydrateDefault(config.default);
  }, [config?.default, hydrateDefault]);

  const claudeAvailable = config ? config.claudeConfigured : true;
  return { provider, setProvider, config, claudeAvailable };
}

export function LlmProviderToggle({
  className,
  size = "md",
}: {
  className?: string;
  size?: "sm" | "md";
}) {
  const { provider, setProvider, claudeAvailable } = useLlmProvider();
  const activeIndex = OPTIONS.findIndex((o) => o.id === provider);

  const pad = size === "sm" ? "p-0.5" : "p-1";
  const seg = size === "sm" ? "px-2 py-1 text-[11px]" : "px-2.5 py-1.5 text-[12px]";
  const icon = size === "sm" ? "size-3" : "size-3.5";

  return (
    <div
      role="radiogroup"
      aria-label="LLM 공급자"
      className={cn(
        "relative inline-grid grid-cols-2 rounded-full border border-border bg-secondary/60",
        pad,
        className
      )}
    >
      {/* sliding thumb — 활성 세그먼트로 이동 (tweakcn 토글의 트랜지션 차용) */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-1 left-1 rounded-full bg-brand shadow-sm transition-transform duration-300 ease-out",
          size === "sm" && "inset-y-0.5 left-0.5"
        )}
        style={{
          width: `calc(50% - ${size === "sm" ? "2px" : "4px"})`,
          transform: activeIndex === 1 ? "translateX(100%)" : "translateX(0)",
        }}
      />

      {OPTIONS.map(({ id, label, short, Icon }) => {
        const active = id === provider;
        const disabled = id === "claude" && !claudeAvailable;
        const btn = (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => setProvider(id)}
            className={cn(
              "relative z-10 flex items-center justify-center gap-1.5 rounded-full font-medium transition-colors",
              seg,
              active
                ? "text-[var(--primary-foreground)]"
                : "text-muted-foreground hover:text-foreground",
              disabled && "cursor-not-allowed opacity-40 hover:text-muted-foreground"
            )}
          >
            <Icon className={icon} />
            <span>{short}</span>
          </button>
        );

        if (disabled) {
          return (
            <Tooltip key={id}>
              <TooltipTrigger asChild>{btn}</TooltipTrigger>
              <TooltipContent>
                {label} — 서버에 ANTHROPIC_API_KEY 가 설정되지 않았습니다.
              </TooltipContent>
            </Tooltip>
          );
        }
        return btn;
      })}
    </div>
  );
}

/** 세션 헤더 등에서 활성 공급자를 읽기 전용 배지로 보여줄 때 사용. */
export function providerLabel(p: LlmProvider | undefined): string {
  return OPTIONS.find((o) => o.id === p)?.label ?? "로컬 LLM";
}
