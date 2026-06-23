"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { TriangleAlert, X } from "lucide-react";

import { completeAnalysis, getSession, queryKeys } from "@/lib/api";
import type { Finding, Question, Session } from "@/lib/types";
import { agentMeta } from "@/lib/constants";
import { useSessionProgress } from "@/lib/sse";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";

import { SessionHeader } from "./SessionHeader";
import { QuestionList } from "./QuestionList";
import { QuestionDetail } from "./QuestionDetail";
import { AnomalyCard } from "./AnomalyCard";
import { MatrixView } from "./MatrixView";
import { RerunPanel } from "./RerunControls";
import { PipelineProgress } from "@/components/progress/PipelineProgress";

export function SessionView({ id }: { id: string }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.session(id),
    queryFn: () => getSession(id),
  });

  const [tab, setTab] = useState("questions");
  const [selectedQ, setSelectedQ] = useState<number | null>(null);

  // 콘텐츠를 스크롤하면 헤더를 축약 모드로 고정.
  // ★ document 에 capture 로 1회 부착 → 어떤 스크롤러(문항 리스트/상세/매트릭스,
  //   심지어 페이지 main)에서 스크롤이 나든 모두 수신. 본문이 로딩 후 마운트돼도
  //   rootRef 는 이벤트 시점에 lazy read 하므로 부착 타이밍 문제가 없다.
  //   필터: scroll target 이 SessionView root 의 내부이거나(내부 패널) 그 조상이면
  //   (page 스크롤) 축약 판정. 사이드바 등 무관한 스크롤은 무시한다.
  const rootRef = useRef<HTMLDivElement>(null);
  const [condensed, setCondensed] = useState(false);
  useEffect(() => {
    let raf = 0;
    let latestTop = 0;
    const apply = () => {
      raf = 0;
      // ★ 오실레이션 차단(짧은 콘텐츠 떨림 버그):
      //   헤더 축약 시 높이가 Δ≈44px 줄어 스크롤러 maxScroll 이 그만큼 감소→scrollTop 클램프.
      //   축약 임계값(72)을 Δ+해제임계값(8)보다 크게 두면, 축약 후에도 잔여 스크롤이 남아
      //   되튐(축약→클램프→해제→재오버플로)이 기하학적으로 불가능해진다.
      setCondensed((prev) => (prev ? latestTop > 8 : latestTop > 72));
    };
    const onScroll = (e: Event) => {
      const root = rootRef.current;
      const t = e.target as Node | null;
      if (!root || !t) return;
      const inside = root.contains(t);
      const isAncestor = t instanceof Element && t.contains(root);
      if (!inside && !isAncestor) return;
      const el =
        t instanceof HTMLElement
          ? t
          : (document.scrollingElement as HTMLElement | null);
      latestTop = el?.scrollTop ?? 0;
      if (!raf) raf = requestAnimationFrame(apply); // 프레임당 1회만 반영
    };
    document.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("scroll", onScroll, true);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  // 탭 전환 시 새 스크롤러는 최상단 → 축약 해제.
  useEffect(() => {
    const raf = requestAnimationFrame(() => setCondensed(false));
    return () => cancelAnimationFrame(raf);
  }, [tab]);

  const firstFoundQ = useMemo(() => {
    if (!data) return null;
    const first = data.findings[0];
    return first?.qNumber ?? data.questions[0]?.qNumber ?? null;
  }, [data]);

  const activeQ = selectedQ ?? firstFoundQ;

  if (isLoading) return <LoadingState />;

  // 서버 미연결(네트워크 오류) — 세션 자체를 불러오지 못함. 재실행 + 재연결 제공.
  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-6">
        <RerunPanel
          sessionId={id}
          variant="disconnected"
          onRetryFetch={() => refetch()}
        />
      </div>
    );
  }
  if (!data) return <NotFoundState />;

  const { session, questions, findings } = data;

  if (session.status === "running" || session.status === "parsing") {
    return <RunningView session={session} questions={questions} />;
  }

  // 분석이 오류로 종료됨 (LLM 서버 미가용 등) — 공급자 전환 후 재실행.
  if (session.status === "error") {
    return (
      <div className="flex h-full flex-col">
        <SessionHeader session={session} />
        <div className="flex flex-1 items-center justify-center p-6">
          <RerunPanel sessionId={session.id} variant="error" />
        </div>
      </div>
    );
  }

  const selectedQuestion =
    questions.find((q) => q.qNumber === activeQ) ?? null;
  const selectedFindings: Finding[] = findings.filter(
    (f) => f.qNumber === activeQ
  );

  const selectAndShow = (q: number) => {
    setSelectedQ(q);
    setTab("questions");
  };

  return (
    <div ref={rootRef} className="flex h-full flex-col">
      <SessionHeader session={session} condensed={condensed} />

      <div className="flex min-h-0 flex-1 flex-col">
      <Tabs
        value={tab}
        onValueChange={setTab}
        className="flex min-h-0 flex-1 flex-col gap-0"
      >
        <div className="border-b border-border px-5 py-2">
          <TabsList>
            <TabsTrigger value="questions">문항별</TabsTrigger>
            <TabsTrigger value="matrix">매트릭스</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="questions" className="min-h-0 flex-1">
          <div className="grid h-full grid-cols-[4fr_6fr] divide-x divide-border">
            <QuestionList
              questions={questions}
              findings={findings}
              selectedQ={activeQ}
              onSelect={setSelectedQ}
            />
            <QuestionDetail
              sessionId={session.id}
              question={selectedQuestion}
              findings={selectedFindings}
            />
          </div>
        </TabsContent>

        <TabsContent value="matrix" className="min-h-0 flex-1 overflow-auto p-5">
          <MatrixView
            questions={questions}
            findings={findings}
            onSelectQ={selectAndShow}
          />
        </TabsContent>
      </Tabs>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-4 p-5">
      <Skeleton className="h-12 w-full" />
      <div className="grid grid-cols-[280px_1fr] gap-4">
        <Skeleton className="h-[60vh] w-full" />
        <Skeleton className="h-[60vh] w-full" />
      </div>
    </div>
  );
}

function NotFoundState({ message }: { message?: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-10 text-center">
      <TriangleAlert className="size-6 text-[var(--status-error)]" />
      <p className="text-[13px] text-muted-foreground">
        {message ?? "세션을 찾을 수 없습니다."}
      </p>
    </div>
  );
}

/**
 * 분석 진행 중 뷰. SSE(useSessionProgress)로 문항 진행 + 실시간 findings 를 받아
 * 진행바/문항 도트를 그리고, 문항을 클릭하면 그 문항에서 탐지된 내용을 즉시 보여준다.
 * (findings 는 q_done 마다 누적되며 백엔드도 증분 영속하므로 새로고침에도 유지된다.)
 */
function RunningView({
  session,
  questions,
}: {
  session: Session;
  questions: Question[];
}) {
  const queryClient = useQueryClient();
  const [selectedQ, setSelectedQ] = useState<number | null>(null);

  const state = useSessionProgress({
    sessionId: session.id,
    totalQ: session.questionCount,
    onDone: (foundCount) => {
      // mock 모드: 로컬 세션을 done 으로 마감. real 모드: 백엔드가 이미 done 을
      // 영속했으므로 no-op (USE_MOCK=false). 양쪽 모두 쿼리를 무효화해 대시보드로 전환.
      completeAnalysis(session.id, foundCount, state.elapsedSeconds);
      queryClient.invalidateQueries({ queryKey: queryKeys.session(session.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });

  const selectedQuestion =
    selectedQ != null
      ? questions.find((q) => q.qNumber === selectedQ) ?? null
      : null;
  const selectedFindings: Finding[] =
    selectedQ != null ? state.findingsByQ[selectedQ] ?? [] : [];
  const selectedStatus =
    selectedQ != null ? state.questionStatus[selectedQ] ?? "pending" : null;
  const selectedLane =
    selectedQ != null ? state.workerByQ[selectedQ] : undefined;

  // 실시간 탐지 피드: findings 가 있는 문항(문항순) + 검토 실패 문항.
  const feedQs = Object.keys(state.findingsByQ)
    .map(Number)
    .filter((q) => (state.findingsByQ[q]?.length ?? 0) > 0)
    .sort((a, b) => a - b);
  const erroredQs = Object.keys(state.questionStatus)
    .map(Number)
    .filter((q) => state.questionStatus[q] === "error")
    .sort((a, b) => a - b);

  return (
    <div className="flex h-full flex-col">
      <SessionHeader session={session} />
      <div className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
          <PipelineProgress
            state={state}
            selectedQ={selectedQ}
            onSelectQ={setSelectedQ}
          />

          {/* 선택한 문항의 실시간 탐지 내용 */}
          {selectedQ != null && (
            <div className="flex flex-col rounded-md border border-border bg-card">
              <div className="flex items-center gap-2 border-b border-border px-3 py-2">
                <span className="font-mono text-xs tabular-nums text-muted-foreground">
                  문항 {String(selectedQ).padStart(2, "0")}
                </span>
                {selectedLane != null && (
                  <span
                    className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium"
                    style={{
                      color: agentMeta(selectedLane).color,
                      backgroundColor: `color-mix(in oklab, ${agentMeta(selectedLane).color} 14%, transparent)`,
                    }}
                  >
                    <span
                      className="size-1.5 rounded-full animate-pulse"
                      style={{ backgroundColor: agentMeta(selectedLane).color }}
                    />
                    {agentMeta(selectedLane).label} 처리 중
                  </span>
                )}
                <span className="h-px flex-1 bg-border" />
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  탐지 {selectedFindings.length}
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedQ(null)}
                  className="text-muted-foreground transition-colors hover:text-foreground"
                  title="닫기"
                >
                  <X className="size-3.5" />
                </button>
              </div>
              <div className="flex flex-col gap-3 p-3">
                {selectedQuestion && (
                  <pre className="whitespace-pre-wrap rounded-md border border-border bg-secondary/30 p-3 font-sans text-[13px] leading-relaxed text-foreground">
                    {selectedQuestion.mdText}
                  </pre>
                )}
                {selectedFindings.length > 0 ? (
                  selectedFindings.map((f) => (
                    <AnomalyCard key={f.id} sessionId={session.id} finding={f} />
                  ))
                ) : (
                  <div className="py-4 text-center text-[13px] text-muted-foreground">
                    {selectedStatus === "error"
                      ? "이 문항은 검토에 실패했습니다(타임아웃/파싱오류). 분석 후 재실행을 권장합니다."
                      : selectedStatus === "done"
                        ? "이 문항에서 탐지된 오류가 없습니다."
                        : "아직 이 문항을 검토 중입니다…"}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 실시간 탐지 피드 — 문항 클릭 없이도 도착하는 대로 검수(확인/반려) */}
          {selectedQ == null && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[15px] font-medium text-foreground">
                  실시간 탐지
                </span>
                <span
                  className="font-mono text-[14px] font-medium tabular-nums"
                  style={{ color: "var(--status-found)" }}
                >
                  {state.foundCount}건
                </span>
                <span className="text-[12px] text-muted-foreground">
                  · 분석 중에도 바로 확인/반려할 수 있습니다
                </span>
              </div>

              {erroredQs.length > 0 && (
                <div
                  className="rounded-md border px-3 py-2 text-[13px]"
                  style={{
                    borderColor: "#f59e0b66",
                    backgroundColor: "#f59e0b14",
                    color: "#f59e0b",
                  }}
                >
                  ⚠️ 검토 실패 {erroredQs.length}문항 (
                  {erroredQs.map((q) => `Q${q}`).join(", ")}) — 분석 완료 후
                  재실행을 권장합니다.
                </div>
              )}

              {feedQs.length === 0 ? (
                <div className="rounded-md border border-dashed border-border py-10 text-center text-[13px] text-muted-foreground">
                  아직 탐지된 오류가 없습니다. 검토가 진행되면 여기에 실시간으로
                  쌓입니다.
                </div>
              ) : (
                feedQs.map((q) => (
                  <div key={q} className="flex flex-col gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedQ(q)}
                      className="flex items-center gap-2 text-left transition-colors hover:text-foreground"
                      title="이 문항만 보기(원문 포함)"
                    >
                      <span className="font-mono text-[13px] tabular-nums text-muted-foreground">
                        문항 {String(q).padStart(2, "0")}
                      </span>
                      <span className="h-px flex-1 bg-border" />
                      <span className="font-mono text-[12px] tabular-nums text-muted-foreground">
                        {state.findingsByQ[q].length}건
                      </span>
                    </button>
                    {state.findingsByQ[q].map((f) => (
                      <AnomalyCard
                        key={f.id}
                        sessionId={session.id}
                        finding={f}
                      />
                    ))}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
