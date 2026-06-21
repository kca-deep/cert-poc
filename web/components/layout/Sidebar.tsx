"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Plus, ScanSearch, Workflow, PanelLeftClose, PanelLeft } from "lucide-react";

import { listSessions, queryKeys } from "@/lib/api";
import { STATUS_META } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useSidebarStore } from "@/lib/stores/sidebar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV: NavItem[] = [
  { href: "/sessions", label: "세션 목록", icon: ScanSearch },
  { href: "/pipeline", label: "파이프라인 안내", icon: Workflow },
];

/**
 * Fixed left rail (webapp_frontend_plan.md §0 app shell).
 * Holds the single filled emerald CTA ("+ 새 분석") plus the live list of
 * analysis sessions, so each dashboard is one click away (Supabase Studio rail).
 *
 * 접힘(최소화) 시 220px → 56px 아이콘 레일로 줄고 라벨은 Tooltip 으로만 노출한다.
 * 상태는 useSidebarStore(localStorage 영속)에 저장 — 새로고침해도 유지.
 */
export function Sidebar() {
  const pathname = usePathname();
  const { data: sessions } = useQuery({
    queryKey: queryKeys.sessions,
    queryFn: listSessions,
  });

  const collapsed = useSidebarStore((s) => s.collapsed);
  const toggle = useSidebarStore((s) => s.toggle);

  // persist 가 localStorage 를 동기적으로 읽어 SSR(false)과 첫 클라이언트 렌더가
  // 어긋나면 hydration 경고가 난다 → mount 전에는 펼침(false)으로 고정.
  const [mounted, setMounted] = useState(false);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- mount 1회 플립(SSR hydration 가드)
  useEffect(() => setMounted(true), []);
  const isCollapsed = mounted && collapsed;

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-out",
        isCollapsed ? "w-[56px]" : "w-[220px]"
      )}
    >
      <div className="flex flex-col gap-4 px-3 py-4">
        {/* Wordmark row — 접힘 시 심볼만, 펼침 시 워드마크+AI 배지 */}
        <div
          className={cn(
            "flex items-center",
            isCollapsed ? "justify-center" : "justify-between"
          )}
        >
          <Link
            href="/sessions"
            className={cn(
              "flex items-center gap-2.5",
              !isCollapsed && "px-1.5"
            )}
            aria-label="CertQA 홈"
          >
            {/* CertQA 심볼 — 솔리드 에메랄드 체크(S1 v1).
                원본: assets/logo/certqa-s1-v1-24.svg. 단일 fill 글리프, 아웃라인 없음. */}
            <svg
              viewBox="0 0 24 24"
              className="size-6 shrink-0"
              aria-hidden="true"
            >
              <path
                fill="var(--brand)"
                d="M8.85 21.35L0.95 13.45L4.75 9.65L8.85 13.75L20.25 2.35L23.05 6.15L8.85 21.35Z"
              />
            </svg>
            {!isCollapsed && (
              <>
                {/* 워드마크 CertQA — Archivo Black(900) 디스플레이 폰트. QA는 에메랄드. */}
                <span
                  className="text-lg tracking-tight whitespace-nowrap text-foreground"
                  style={{ fontFamily: "var(--font-archivo)", fontWeight: 900 }}
                >
                  Cert<span className="text-[var(--brand)]">QA</span>
                </span>
                {/* AI 배지 — 무채색 칩. 에메랄드(QA) 외 색상 이벤트를 만들지 않는다. */}
                <span className="rounded border border-border px-1.5 py-0.5 text-[10px] font-medium uppercase leading-none tracking-wide text-muted-foreground">
                  AI
                </span>
              </>
            )}
          </Link>
          {!isCollapsed && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggle}
              aria-label="사이드바 접기"
              aria-expanded
            >
              <PanelLeftClose className="size-4" />
            </Button>
          )}
        </div>

        {/* 접힘 상태 펼치기 버튼 — 워드마크 아래 별도 행(아이콘 중앙 정렬) */}
        {isCollapsed && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={toggle}
                aria-label="사이드바 펼치기"
                aria-expanded={false}
                className="self-center"
              >
                <PanelLeft className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">사이드바 펼치기</TooltipContent>
          </Tooltip>
        )}

        {/* The one filled green CTA */}
        {isCollapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button asChild size="icon-sm" className="self-center">
                <Link href="/upload" aria-label="새 분석">
                  <Plus className="size-3.5" />
                </Link>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">새 분석</TooltipContent>
          </Tooltip>
        ) : (
          <Button asChild size="sm" className="w-full justify-start gap-1.5">
            <Link href="/upload">
              <Plus className="size-3.5" />새 분석
            </Link>
          </Button>
        )}

        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/sessions"
                ? pathname === "/sessions"
                : pathname === href || pathname.startsWith(`${href}/`);
            const link = (
              <Link
                href={href}
                data-active={active}
                aria-label={label}
                className={cn(
                  "flex items-center gap-2 rounded-md text-[13px] font-medium transition-colors",
                  isCollapsed
                    ? "justify-center px-2 py-2"
                    : "px-2 py-1.5",
                  active
                    ? "bg-sidebar-accent text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground"
                )}
              >
                <Icon className="size-4" />
                {!isCollapsed && (
                  <span className="whitespace-nowrap">{label}</span>
                )}
              </Link>
            );
            return isCollapsed ? (
              <Tooltip key={href}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ) : (
              <div key={href}>{link}</div>
            );
          })}
        </nav>
      </div>

      {/* Live session list — 접힘 시 텍스트 위주라 숨긴다(펼치면 다시 노출) */}
      {!isCollapsed && (
        <div className="flex min-h-0 flex-1 flex-col border-t border-sidebar-border">
          <div className="flex items-center justify-between px-4 pt-3 pb-1.5">
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              분석 세션
            </span>
            {sessions && (
              <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                {sessions.length}
              </span>
            )}
          </div>

          <ScrollArea className="flex-1">
            <ul className="flex flex-col gap-0.5 px-2 pb-3">
              {sessions?.map((s) => {
                const active = pathname === `/sessions/${s.id}`;
                const tone = STATUS_META[s.status].tone;
                return (
                  <li key={s.id}>
                    <Link
                      href={`/sessions/${s.id}`}
                      data-active={active}
                      className={cn(
                        "group flex flex-col gap-0.5 rounded-md px-2 py-1.5 transition-colors",
                        active
                          ? "bg-sidebar-accent"
                          : "hover:bg-sidebar-accent/60"
                      )}
                    >
                      <div className="flex items-center gap-1.5">
                        <span
                          className={cn(
                            "size-1.5 shrink-0 rounded-full",
                            tone === "active" && "animate-pulse"
                          )}
                          style={{
                            backgroundColor:
                              tone === "done"
                                ? "var(--status-found)"
                                : tone === "active"
                                  ? "var(--layer-2)"
                                  : tone === "error"
                                    ? "var(--status-error)"
                                    : "var(--muted-foreground)",
                          }}
                        />
                        <span
                          className={cn(
                            "truncate text-[12px]",
                            active
                              ? "text-foreground"
                              : "text-muted-foreground group-hover:text-foreground"
                          )}
                          title={s.originalFilename}
                        >
                          {s.originalFilename}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 pl-3 font-mono text-[10px] text-muted-foreground">
                        <span className="uppercase">{s.fileType}</span>
                        <span>문항 {s.questionCount}</span>
                        <span
                          className={
                            s.foundCount > 0 ? "text-[var(--status-found)]" : ""
                          }
                        >
                          탐지 {s.foundCount}
                        </span>
                      </div>
                    </Link>
                  </li>
                );
              })}
              {sessions && sessions.length === 0 && (
                <li className="px-2 py-3 text-[11px] text-muted-foreground">
                  세션이 없습니다.
                </li>
              )}
            </ul>
          </ScrollArea>
        </div>
      )}

      {/* 접힘 시 세션 리스트가 사라지므로 레일을 끝까지 채우는 spacer */}
      {isCollapsed && <div className="flex-1" />}

      {!isCollapsed && (
        <div className="border-t border-sidebar-border px-3 py-2.5">
          <p className="text-[11px] leading-tight text-muted-foreground">
            자격검정 문항 오류 검출
          </p>
        </div>
      )}
    </aside>
  );
}
