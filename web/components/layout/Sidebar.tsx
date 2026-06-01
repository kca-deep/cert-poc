"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Plus, ScanSearch } from "lucide-react";

import { listSessions, queryKeys } from "@/lib/api";
import { STATUS_META } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV: NavItem[] = [
  { href: "/sessions", label: "세션 목록", icon: ScanSearch },
];

/**
 * Fixed ~200px left rail (webapp_frontend_plan.md §0 app shell).
 * Holds the single filled emerald CTA ("+ 새 분석") plus the live list of
 * analysis sessions, so each dashboard is one click away (Supabase Studio rail).
 */
export function Sidebar() {
  const pathname = usePathname();
  const { data: sessions } = useQuery({
    queryKey: queryKeys.sessions,
    queryFn: listSessions,
  });

  return (
    <aside className="flex w-[220px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex flex-col gap-4 px-3 py-4">
        {/* Wordmark — emerald is the only chromatic event */}
        <Link href="/sessions" className="flex items-center gap-2.5 px-1.5">
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
          {/* 워드마크 CertQA — Archivo Black(900) 디스플레이 폰트.
              QA는 에메랄드 색으로 구분. */}
          <span
            className="text-lg tracking-tight text-foreground"
            style={{ fontFamily: "var(--font-archivo)", fontWeight: 900 }}
          >
            Cert<span className="text-[var(--brand)]">QA</span>
          </span>
        </Link>

        {/* The one filled green CTA */}
        <Button asChild size="sm" className="w-full justify-start gap-1.5">
          <Link href="/upload">
            <Plus className="size-3.5" />새 분석
          </Link>
        </Button>

        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/sessions"
                ? pathname === "/sessions"
                : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                data-active={active}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] font-medium transition-colors",
                  active
                    ? "bg-sidebar-accent text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground"
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Live session list — each row links straight to its dashboard */}
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

      <div className="border-t border-sidebar-border px-3 py-2.5">
        <p className="text-[11px] leading-tight text-muted-foreground">
          자격검정 문항 오류 검출
        </p>
      </div>
    </aside>
  );
}
