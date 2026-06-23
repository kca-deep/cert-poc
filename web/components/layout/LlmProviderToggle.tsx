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
import type { LlmConfig, LlmProvider, ProviderMeta } from "@/lib/types";
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

  const configLoaded = config !== undefined;
  const configAvailable = config != null;
  const claudeAvailable = configAvailable ? config.claudeConfigured : false;
  const localAvailable = configAvailable
    ? (config.providers.find((p) => p.id === "local")?.available ?? true)
    : false;

  useEffect(() => {
    if (config?.default) hydrateDefault(config.default);
  }, [config?.default, hydrateDefault]);

  useEffect(() => {
    if (!configAvailable) return;
    const activeAvailable =
      provider === "claude" ? claudeAvailable : localAvailable;
    if (activeAvailable) return;
    const next = config?.providers.find((p) => p.available)?.id;
    if (next && next !== provider) setProvider(next);
  }, [claudeAvailable, config, configAvailable, localAvailable, provider, setProvider]);

  return {
    provider,
    setProvider,
    config,
    configLoaded,
    claudeAvailable,
    localAvailable,
  };
}

export function LlmProviderToggle({
  className,
  size = "md",
}: {
  className?: string;
  size?: "sm" | "md";
}) {
  const { provider, setProvider, config, claudeAvailable, localAvailable } =
    useLlmProvider();
  const localMeta = config?.providers.find((p) => p.id === "local");
  const cols = OPTIONS.length;
  const activeIndex = Math.max(0, OPTIONS.findIndex((o) => o.id === provider));

  const pad = size === "sm" ? "p-0.5" : "p-1";
  const seg = size === "sm" ? "px-2 py-1 text-[11px]" : "px-2.5 py-1.5 text-[12px]";
  const icon = size === "sm" ? "size-3" : "size-3.5";
  // thumb 너비 = (트랙 내부폭)/cols. 내부폭은 좌우 패딩(sm 2px·md 4px → 총 4px·8px)을 뺀 값.
  const padTotal = size === "sm" ? 4 : 8;

  return (
    <div
      role="radiogroup"
      aria-label="LLM 공급자"
      className={cn(
        "relative inline-grid rounded-full border border-border bg-secondary/60",
        pad,
        className
      )}
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {/* sliding thumb — 활성 세그먼트로 이동 (tweakcn 토글의 트랜지션 차용) */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-1 left-1 rounded-full bg-brand shadow-sm transition-transform duration-300 ease-out",
          size === "sm" && "inset-y-0.5 left-0.5"
        )}
        style={{
          width: `calc(${100 / cols}% - ${padTotal}px / ${cols})`,
          transform: `translateX(${activeIndex * 100}%)`,
        }}
      />

      {OPTIONS.map(({ id, label, short, Icon }) => {
        const active = id === provider;
        const disabled =
          (id === "claude" && !claudeAvailable) ||
          (id === "local" && !localAvailable);
        const reason =
          id === "claude"
            ? `${label} — 서버에 ANTHROPIC_API_KEY 가 설정되지 않았습니다.`
            : `${label} — 서버 응답이 없습니다. LLM 서버(LOCAL_BASE_URLS) 실행 여부를 확인하세요.`;
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
              <TooltipContent>{reason}</TooltipContent>
            </Tooltip>
          );
        }
        // 로컬(Ollama 등) 가용 시 — 탐지된 모델명과 실행/설치 상태를 툴팁으로 안내.
        if (id === "local" && localMeta?.model) {
          return (
            <Tooltip key={id}>
              <TooltipTrigger asChild>{btn}</TooltipTrigger>
              <TooltipContent>{localStatusText(localMeta)}</TooltipContent>
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

/**
 * 모델 ID(예: "EXAONE-3.5-32B", "claude-haiku-4-5") → 사람이 읽을 짧은 이름.
 * 로컬 모델이 차수마다 바뀔 수 있어(EXAONE/gpt-oss) 알려진 패턴만 정규화하고,
 * 매칭이 없으면 모델 ID 를 그대로 노출한다.
 */
/**
 * 로컬 공급자 툴팁 문구 — 탐지된 모델명 + 백엔드/실행 상태.
 * Ollama 는 loaded(=메모리 로딩)로 "실행중/설치됨(미로딩)"을 구분하고,
 * llama.cpp/LM Studio(loaded=null)는 모델명만 노출한다.
 */
function localStatusText(meta: ProviderMeta): string {
  // raw 모델 id 도 함께 보여줘 차수별 정확한 태그(exaone3.5:32b 등)를 확인 가능.
  const name = meta.model === prettyModel(meta.model)
    ? meta.model
    : `${prettyModel(meta.model)} (${meta.model})`;
  if (meta.backend === "ollama") {
    return meta.loaded ? `${name} · 실행중` : `${name} · 설치됨(미로딩)`;
  }
  return name;
}

function prettyModel(model: string): string {
  const m = model.toLowerCase();
  // exaone 은 버전/크기(4.0-32B 등)가 중요하므로 뭉개지 않고 전체 id 를 그대로
  // 노출한다 (gemma4 와 동일 취급 — 아래 return model 로 폴백).
  if (m.includes("haiku")) return "Claude Haiku";
  if (m.includes("sonnet")) return "Claude Sonnet";
  if (m.includes("opus")) return "Claude Opus";
  if (m.includes("gpt-oss")) return "gpt-oss";
  return model;
}

/**
 * provider → 현재 옵션(GET /config/llm)에 맞춘 실제 모델 라벨.
 * config 가 있으면 로딩된 모델명(EXAONE 등)을, 없으면 정적 공급자 라벨로 폴백.
 * (토글의 "현재 사용할 모델" 표시용 — 실시간 상태)
 */
export function providerModelLabel(
  p: LlmProvider | undefined,
  config?: LlmConfig | null,
): string {
  const meta = config?.providers.find((o) => o.id === p);
  if (meta?.model) return prettyModel(meta.model);
  return providerLabel(p);
}

/**
 * 세션이 "분석 시점에 실제로 사용한" 모델 라벨.
 * 저장된 model id 가 있으면 그것을(gpt-oss/exaone 구분), 없으면(구 세션) 일반
 * 공급자 라벨로 폴백한다. 실시간 config 를 보지 않으므로 현재 서빙 모델로 오표기되지
 * 않는다 — 세션 목록/헤더는 이 함수를 쓴다.
 */
export function sessionModelLabel(
  p: LlmProvider | undefined,
  model?: string | null,
): string {
  if (model) return prettyModel(model);
  return providerLabel(p);
}
