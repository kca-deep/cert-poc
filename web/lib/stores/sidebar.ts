/**
 * 좌측 사이드바 접힘(최소화) 상태.
 *
 * localStorage 에 영속하므로 새로고침 후에도 마지막 펼침/접힘 상태가 유지된다
 * (provider.ts 와 동일한 zustand+persist 패턴). 접히면 사이드바는 아이콘만 남는
 * 56px 레일이 되고 main 영역이 자동으로 넓어진다(layout.tsx 의 flex 레이아웃).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SidebarState {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (v: boolean) => void;
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      collapsed: false,
      toggle: () => set((s) => ({ collapsed: !s.collapsed })),
      setCollapsed: (collapsed) => set({ collapsed }),
    }),
    { name: "certqa-sidebar-collapsed" }
  )
);
