/**
 * lib/sse.ts — 파이프라인 진행 상태 훅.
 *
 * 한 훅으로 두 모드를 모두 지원한다 (NEXT_PUBLIC_USE_MOCK 로 분기):
 *   - mock : 타이머로 ProgressEvent 를 생성해 클라이언트에서 시뮬레이션
 *   - real : `${API_BASE}/sessions/{id}/progress` 의 SSE(EventSource)를 구독
 *
 * 두 모드 모두 동일한 reduce(reduceEvent) 로 ProgressEvent → ProgressState 를
 * 만든다 → 이벤트 처리 로직이 한 곳에만 존재(이중관리 없음). 백엔드 SSE 이벤트
 * 키는 src/core/events.py(=web/lib/types.ts ProgressEvent)의 camelCase 와
 * 정확히 일치하므로 무변환으로 소비한다.
 *
 * 반환 타입(ProgressState)과 훅 시그니처는 PipelineProgress 의 계약이다.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import type { Layer, ProgressEvent } from "./types";
import { API_BASE } from "./api";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";

// ---------------------------------------------------------------------------
// Exported types (contract — PipelineProgress 가 의존)
// ---------------------------------------------------------------------------

export type ProgressPhase =
  | "starting"
  | "layer0"
  | "layer1"
  | "layer2"
  | "postprocess"
  | "done"
  | "error";

export interface LayerProgress {
  layer: Layer;
  status: "pending" | "active" | "done";
  processed: number;
  totalQ: number;
  found: number;
  currentType?: string; // 가장 최근 처리한 유형 코드 (진행 중 표시용, L1/L2)
  currentQ?: number; // 가장 최근 처리한 문항 번호
}

export type QuestionDotStatus = "pending" | "active" | "done";

export interface ProgressState {
  phase: ProgressPhase;
  layers: LayerProgress[]; // 항상 3개 (L0, L1, L2)
  questionStatus: Record<number, QuestionDotStatus>;
  totalQ: number;
  foundCount: number;
  filteredCount: number; // 후처리 필터로 제거된 오탐 건수 (postprocess 이벤트)
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

function makeLayers(totalQ: number): LayerProgress[] {
  return ([0, 1, 2] as Layer[]).map((l) => ({
    layer: l,
    status: "pending" as const,
    processed: 0,
    totalQ,
    found: 0,
  }));
}

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
    layers: makeLayers(totalQ),
    questionStatus: makeQuestionStatus(totalQ),
    totalQ,
    foundCount: 0,
    filteredCount: 0,
    elapsedSeconds: 0,
  };
}

function doneCount(qs: Record<number, QuestionDotStatus>): number {
  let n = 0;
  for (const v of Object.values(qs)) if (v === "done") n++;
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
    case "layer_start": {
      const idx = ev.layer as number;
      const totalQ = ev.totalQ ?? prev.totalQ;
      const layers = prev.layers.map((l, i) =>
        i === idx ? { ...l, status: "active" as const, totalQ } : l
      );
      // L1, L2 진입 시 문항 도트를 새로 채운다 (레이어마다 전 문항 재순회).
      const questionStatus =
        idx > 0 ? makeQuestionStatus(totalQ) : prev.questionStatus;
      const phase = `layer${idx}` as ProgressPhase;
      return { ...prev, phase, layers, questionStatus, totalQ };
    }

    case "q_layer0_done": {
      const qs = { ...prev.questionStatus, [ev.q]: "done" as const };
      const foundHere = Object.values(ev.types).filter(Boolean).length;
      const layers = prev.layers.map((l, i) =>
        i === 0
          ? { ...l, processed: doneCount(qs), found: l.found + foundHere, currentQ: ev.q }
          : l
      );
      return {
        ...prev,
        questionStatus: qs,
        layers,
        foundCount: prev.foundCount + foundHere,
      };
    }

    case "q_type_done": {
      const idx = ev.layer as number;
      const qs = { ...prev.questionStatus, [ev.q]: "done" as const };
      const layers = prev.layers.map((l, i) =>
        i === idx
          ? {
              ...l,
              processed: doneCount(qs),
              found: l.found + (ev.found ? 1 : 0),
              currentType: ev.typeCode,
              currentQ: ev.q,
            }
          : l
      );
      return {
        ...prev,
        questionStatus: qs,
        layers,
        foundCount: prev.foundCount + (ev.found ? 1 : 0),
      };
    }

    case "layer_done": {
      const idx = ev.layer as number;
      const layers = prev.layers.map((l, i) =>
        i === idx ? { ...l, status: "done" as const, found: ev.found } : l
      );
      return { ...prev, layers };
    }

    case "postprocess":
      return { ...prev, phase: "postprocess", filteredCount: ev.filtered };

    case "done":
      return {
        ...prev,
        phase: "done",
        foundCount: ev.totalFound,
        elapsedSeconds: ev.elapsed,
        layers: prev.layers.map((l) => ({ ...l, status: "done" as const })),
      };

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
  onDoneRef.current = onDone;

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessionId, totalQ]);

  return state;
}

// ---------------------------------------------------------------------------
// real: EventSource 구독
// ---------------------------------------------------------------------------

const EVENT_NAMES = [
  "layer_start",
  "q_layer0_done",
  "q_type_done",
  "layer_done",
  "postprocess",
  "done",
  "error",
] as const;

function startEventSource(
  sessionId: string,
  emit: (ev: ProgressEvent) => void,
  isCancelled: () => boolean
): () => void {
  const url = `${API_BASE}/sessions/${sessionId}/progress`;
  const es = new EventSource(url);

  // 백엔드(sse_starlette)는 `event: <name>` 으로 named event 를 보내므로
  // 7종 모두 addEventListener 로 등록한다. data 는 ProgressEvent JSON.
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
    // 연결 오류: done 전이면 error 이벤트로 표면화하고 닫는다.
    if (isCancelled()) return;
    emit({ event: "error", message: "진행 스트림 연결이 끊겼습니다." });
    es.close();
  };

  return () => es.close();
}

// ---------------------------------------------------------------------------
// mock: 타이머로 ProgressEvent 생성 (real 과 동일 reduce 로 소비)
// ---------------------------------------------------------------------------

/** 대략 5–9건이 잡히도록 하는 결정적 found 규칙 (Math.random 미사용). */
function isFound(q: number, layer: number): boolean {
  return (q * 7 + layer * 3) % 5 === 0;
}

function stepInterval(totalQ: number): number {
  const raw = Math.floor(9000 / Math.max(1, totalQ * 3));
  return Math.max(80, Math.min(200, raw));
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

  const simulateLayer = (layer: Layer) => {
    at(0, () => emit({ event: "layer_start", layer, totalQ }));
    let layerFound = 0;
    for (let q = 1; q <= totalQ; q++) {
      const thisQ = q;
      const found = isFound(q, layer);
      at(interval, () => {
        if (layer === 0) {
          emit({ event: "q_layer0_done", q: thisQ, types: { A01: found } });
        } else {
          emit({
            event: "q_type_done",
            layer,
            q: thisQ,
            typeCode: "A01",
            found,
            ...(found ? { confidence: "medium" as const } : {}),
          });
        }
      });
      if (found) {
        layerFound += 1;
        foundTotal += 1;
      }
    }
    at(interval, () => emit({ event: "layer_done", layer, found: layerFound }));
  };

  simulateLayer(0);
  simulateLayer(1);
  simulateLayer(2);
  at(300, () => emit({ event: "postprocess", filtered: 2 }));
  at(500, () =>
    emit({ event: "done", totalFound: foundTotal, elapsed: cursor / 1000 })
  );

  return () => timers.forEach((t) => clearTimeout(t));
}
