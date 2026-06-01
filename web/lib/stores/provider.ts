/**
 * LLM 공급자 토글 상태 — 분석/재실행이 사용할 활성 공급자.
 *
 * localStorage 에 영속하므로 새 분석/재실행 사이에 선택이 유지된다(=기존 세션
 * 재실행 시에도 마지막 선택이 기본값). 백엔드 GET /config/llm 의 default 로
 * 1회 초기화하며, 사용자가 토글하면 그 값이 우선한다.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { LlmProvider } from "../types";

interface ProviderState {
  provider: LlmProvider;
  /** 사용자가 직접 토글했는지 (true 면 서버 default 로 덮어쓰지 않음). */
  userPicked: boolean;
  setProvider: (p: LlmProvider) => void;
  /** 서버 default 로 초기화 — 사용자가 아직 고르지 않았을 때만 적용. */
  hydrateDefault: (p: LlmProvider) => void;
}

export const useProviderStore = create<ProviderState>()(
  persist(
    (set, get) => ({
      provider: "local",
      userPicked: false,
      setProvider: (provider) => set({ provider, userPicked: true }),
      hydrateDefault: (p) => {
        if (!get().userPicked) set({ provider: p });
      },
    }),
    { name: "certqa-llm-provider" }
  )
);
