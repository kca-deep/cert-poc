/**
 * lib/sse.ts — 파이프라인 진행 상태 훅 (holistic 문항단위).
 *
 * 한 훅으로 두 모드를 모두 지원한다 (NEXT_PUBLIC_USE_MOCK 로 분기):
 *   - mock : 타이머로 ProgressEvent 를 생성해 클라이언트에서 시뮬레이션
 *   - real : `${API_BASE}/sessions/{id}/progress` 의 SSE(EventSource)를 구독
 *
 * 두 모드 모두 동일한 reduce(reduceEvent) 로 ProgressEvent → ProgressState 를
 * 만든다. 백엔드 SSE 이벤트 키는 src/core/events.py(=web/lib/types.ts ProgressEvent)
 * 의 camelCase 와 정확히 일치하므로 무변환으로 소비한다.
 *
 * ★ holistic 전환: 레이어/유형 단위 진행을 폐기하고 **문항 단위**(start·q_done·done)
 *   진행으로 재작성. ProgressState 는 문항 도트 + 누적 findings 건수만 추적한다.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import type { Finding, ProgressEvent } from "./types";
import { API_BASE } from "./api";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";

// ---------------------------------------------------------------------------
// Exported types (contract — PipelineProgress 가 의존)
// ---------------------------------------------------------------------------

export type ProgressPhase = "starting" | "running" | "done" | "error";

export type QuestionDotStatus = "pending" | "active" | "done" | "error";

export interface ProgressState {
  phase: ProgressPhase;
  questionStatus: Record<number, QuestionDotStatus>;
  findingsByQ: Record<number, Finding[]>; // 문항별 실시간 findings (q_done 누적)
  workerByQ: Record<number, number>; // 현재 처리 중 문항 → 논리 레인(agentA/B/C)
  totalQ: number;
  processed: number; // 검토 끝난 문항 수(완료+실패)
  errorQ: number; // 오류가 1건 이상 탐지된 문항 수
  erroredQ: number; // 검토 실패(타임아웃/파싱오류) 문항 수
  foundCount: number; // 누적 findings 건수
  elapsedSeconds: number;
  error?: string;
}

export interface UseSessionProgressOptions {
  sessionId: string;
  totalQ: number;
  enabled?: boolean;
  onDone?: (foundCount: number) => void;
}

// ---------------------------------------------------------------------------
// 초기 상태 + reduce (mock/real 공유)
// ---------------------------------------------------------------------------

function makeQuestionStatus(
  totalQ: number,
  initial: QuestionDotStatus = "pending"
): Record<number, QuestionDotStatus> {
  const m: Record<number, QuestionDotStatus> = {};
  for (let q = 1; q <= totalQ; q++) m[q] = initial;
  return m;
}

function initialState(totalQ: number): ProgressState {
  return {
    phase: "starting",
    questionStatus: makeQuestionStatus(totalQ),
    findingsByQ: {},
    workerByQ: {},
    totalQ,
    processed: 0,
    errorQ: 0,
    erroredQ: 0,
    foundCount: 0,
    elapsedSeconds: 0,
  };
}

// 검토가 끝난(완료 또는 실패) 문항 수.
function processedCount(qs: Record<number, QuestionDotStatus>): number {
  let n = 0;
  for (const v of Object.values(qs)) if (v === "done" || v === "error") n++;
  return n;
}

/**
 * 단일 ProgressEvent 를 받아 다음 ProgressState 를 만든다 (순수 함수).
 * mock(타이머 생성)과 real(EventSource 수신) 양쪽이 공유한다.
 */
export function reduceEvent(
  prev: ProgressState,
  ev: ProgressEvent
): ProgressState {
  switch (ev.event) {
    case "start": {
      const totalQ = ev.totalQ ?? prev.totalQ;
      return {
        ...prev,
        phase: "running",
        totalQ,
        questionStatus: makeQuestionStatus(totalQ),
        findingsByQ: {},
        workerByQ: {},
        processed: 0,
        errorQ: 0,
        erroredQ: 0,
        foundCount: 0,
      };
    }

    case "q_start": {
      // 워커가 문항을 집어듦 → active(깜빡임) + 레인(agent) 기록. 이미 끝난 문항이면
      // (이벤트 순서 역전/replay) 유지한다.
      const st = prev.questionStatus[ev.q];
      if (st === "done" || st === "error") return prev;
      return {
        ...prev,
        questionStatus: { ...prev.questionStatus, [ev.q]: "active" as const },
        workerByQ: { ...prev.workerByQ, [ev.q]: ev.worker },
      };
    }

    case "q_done": {
      // error 가 있으면 '검토 실패'(타임아웃/파싱오류) — done 과 구분.
      const errored = !!ev.error;
      const qs = {
        ...prev.questionStatus,
        [ev.q]: (errored ? "error" : "done") as QuestionDotStatus,
      };
      // 실패 문항은 findings 없음. 정상 문항은 q 키로 덮어쓰기(replay 멱등).
      const findingsByQ = {
        ...prev.findingsByQ,
        [ev.q]: errored ? [] : ev.findings ?? [],
      };
      const workerByQ = { ...prev.workerByQ };
      delete workerByQ[ev.q];
      let foundCount = 0;
      let errorQ = 0;
      for (const fs of Object.values(findingsByQ)) {
        foundCount += fs.length;
        if (fs.length > 0) errorQ += 1;
      }
      let erroredQ = 0;
      for (const v of Object.values(qs)) if (v === "error") erroredQ += 1;
      return {
        ...prev,
        questionStatus: qs,
        processed: processedCount(qs),
        findingsByQ,
        workerByQ,
        errorQ,
        erroredQ,
        foundCount,
      };
    }

    case "done": {
      // 검토 실패 문항은 'error' 로 유지(완료로 덮지 않음).
      const qs: Record<number, QuestionDotStatus> = {};
      for (let q = 1; q <= prev.totalQ; q++) {
        qs[q] = prev.questionStatus[q] === "error" ? "error" : "done";
      }
      return {
        ...prev,
        phase: "done",
        foundCount: ev.totalFound,
        elapsedSeconds: ev.elapsed,
        questionStatus: qs,
        processed: prev.totalQ,
      };
    }

    case "error":
      return { ...prev, phase: "error", error: ev.message };

    default:
      return prev;
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSessionProgress(
  opts: UseSessionProgressOptions
): ProgressState {
  const { sessionId, totalQ, enabled = true, onDone } = opts;

  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  const [state, setState] = useState<ProgressState>(() =>
    initialState(totalQ)
  );

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    const cleanups: Array<() => void> = [];

    // 경과 시간 티커 (mock/real 공통). done 이벤트가 백엔드 elapsed 로 덮어쓴다.
    let elapsed = 0;
    const ticker = setInterval(() => {
      if (cancelled) return;
      elapsed += 1;
      setState((p) =>
        p.phase === "done" || p.phase === "error"
          ? p
          : { ...p, elapsedSeconds: elapsed }
      );
    }, 1000);
    cleanups.push(() => clearInterval(ticker));

    const emit = (ev: ProgressEvent) => {
      if (cancelled) return;
      setState((p) => reduceEvent(p, ev));
      if (ev.event === "done") onDoneRef.current?.(ev.totalFound);
    };

    if (USE_MOCK) {
      cleanups.push(startMockSimulation(totalQ, emit, () => cancelled));
    } else {
      cleanups.push(startEventSource(sessionId, emit, () => cancelled));
    }

    return () => {
      cancelled = true;
      cleanups.forEach((fn) => fn());
    };
  }, [enabled, sessionId, totalQ]);

  return state;
}

// ---------------------------------------------------------------------------
// real: EventSource 구독
// ---------------------------------------------------------------------------

const EVENT_NAMES = ["start", "q_start", "q_done", "done", "error"] as const;

function startEventSource(
  sessionId: string,
  emit: (ev: ProgressEvent) => void,
  isCancelled: () => boolean
): () => void {
  const url = `${API_BASE}/sessions/${sessionId}/progress`;
  const es = new EventSource(url);

  // 백엔드(sse_starlette)는 `event: <name>` 으로 named event 를 보낸다.
  const handler = (e: MessageEvent) => {
    if (isCancelled()) return;
    try {
      const ev = JSON.parse(e.data) as ProgressEvent;
      emit(ev);
      if (ev.event === "done" || ev.event === "error") es.close();
    } catch {
      /* malformed frame — ignore */
    }
  };

  for (const name of EVENT_NAMES) {
    es.addEventListener(name, handler as EventListener);
  }
  es.onerror = () => {
    if (isCancelled()) return;
    emit({ event: "error", message: "진행 스트림 연결이 끊겼습니다." });
    es.close();
  };

  return () => es.close();
}

// ---------------------------------------------------------------------------
// mock: 타이머로 ProgressEvent 생성 (real 과 동일 reduce 로 소비)
// ---------------------------------------------------------------------------

const MOCK_TYPES = [
  "맞춤법",
  "띄어쓰기",
  "선택지중복",
  "용어오류",
  "약어오기",
] as const;

/** 대략 1/5 문항에서 오류가 잡히도록 하는 결정적 규칙 (Math.random 미사용). */
function mockFindings(q: number): Finding[] {
  if (q % 5 !== 0) return [];
  return [
    {
      id: `${q}-0`,
      qNumber: q,
      location: "보기 ②",
      quote: "예시 인용",
      errorType: MOCK_TYPES[q % MOCK_TYPES.length],
      reason: "데모용 합성 오류",
      suggestion: "수정안",
      confidence: "보통",
    },
  ];
}

function stepInterval(totalQ: number): number {
  const raw = Math.floor(6000 / Math.max(1, totalQ));
  return Math.max(80, Math.min(260, raw));
}

function startMockSimulation(
  totalQ: number,
  emit: (ev: ProgressEvent) => void,
  isCancelled: () => boolean
): () => void {
  const timers: ReturnType<typeof setTimeout>[] = [];
  const interval = stepInterval(totalQ);
  let cursor = 0;
  let foundTotal = 0;

  const at = (deltaMs: number, fn: () => void) => {
    cursor += deltaMs;
    timers.push(
      setTimeout(() => {
        if (!isCancelled()) fn();
      }, cursor)
    );
  };

  at(0, () => emit({ event: "start", totalQ }));
  for (let q = 1; q <= totalQ; q++) {
    const thisQ = q;
    const errored = thisQ % 7 === 0; // 데모: 7의 배수 문항은 검토 실패로 시뮬레이션
    const findings = errored ? [] : mockFindings(q);
    foundTotal += findings.length;
    at(0, () => emit({ event: "q_start", q: thisQ, worker: (thisQ - 1) % 3 }));
    at(interval, () =>
      emit(
        errored
          ? { event: "q_done", q: thisQ, hasError: false, findings: [], error: "검토 실패(데모)" }
          : { event: "q_done", q: thisQ, hasError: findings.length > 0, findings }
      )
    );
  }
  at(500, () =>
    emit({ event: "done", totalFound: foundTotal, elapsed: cursor / 1000 })
  );

  return () => timers.forEach((t) => clearTimeout(t));
}
