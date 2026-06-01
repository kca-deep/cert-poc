"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";

import { completeAnalysis, getSession, queryKeys } from "@/lib/api";
import type { AnomalyResult, Session } from "@/lib/types";
import { useSessionProgress } from "@/lib/sse";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";

import { SessionHeader } from "./SessionHeader";
import { QuestionList } from "./QuestionList";
import { QuestionDetail } from "./QuestionDetail";
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
  useEffect(() => setCondensed(false), [tab]);

  const firstFoundQ = useMemo(() => {
    if (!data) return null;
    const found = data.results.find((r) => r.found);
    return found?.qNumber ?? data.questions[0]?.qNumber ?? null;
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

  const { session, questions, results } = data;

  if (session.status === "running" || session.status === "parsing") {
    return <RunningView session={session} />;
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
  const selectedResults: AnomalyResult[] = results.filter(
    (r) => r.qNumber === activeQ
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
          <div className="grid h-full grid-cols-[minmax(220px,300px)_1fr] divide-x divide-border">
            <QuestionList
              questions={questions}
              results={results}
              selectedQ={activeQ}
              onSelect={setSelectedQ}
            />
            <QuestionDetail
              sessionId={session.id}
              question={selectedQuestion}
              results={selectedResults}
            />
          </div>
        </TabsContent>

        <TabsContent value="matrix" className="min-h-0 flex-1 overflow-auto p-5">
          <MatrixView
            questions={questions}
            results={results}
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
 * Drives a running session to completion via the mock progress hook, then
 * marks it done and refetches so the dashboard view takes over.
 */
function RunningView({ session }: { session: Session }) {
  const queryClient = useQueryClient();

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

  return (
    <div className="flex h-full flex-col">
      <SessionHeader session={session} />
      {/* 진행 카드를 가용 영역의 가로·세로 중앙에 배치 (내용이 길면 스크롤). */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="flex min-h-full items-center justify-center">
          <div className="w-full max-w-2xl">
            <PipelineProgress state={state} />
          </div>
        </div>
      </div>
    </div>
  );
}
