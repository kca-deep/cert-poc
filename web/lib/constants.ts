/**
 * Catalog + display metadata (holistic findings).
 *
 * ★ 전면 대체: A01~A21 유형 카탈로그 + 레이어 메타를 폐기하고, holistic error_type
 *   11-enum 의 표시 메타로 교체. 색은 globals.css 의 도메인 토큰을 재사용한다.
 */

import type {
  Confidence,
  ErrorType,
  ReviewActionType,
  SessionStatus,
} from "./types";

export interface ErrorTypeMeta {
  code: ErrorType;
  label: string; // 표시 한글명 (= code)
  category: string; // 묶음(칩 색 그룹)
  color: string; // 칩 색 (globals.css 도메인 토큰 hex)
}

/**
 * error_type 11-enum 표시 메타 (삽입 순서 = 표시 순서).
 * category 로 묶어 색을 부여한다: 표기 / 문장 / 선택지 / 내용 / 치명 / 기타.
 */
export const ERROR_TYPES: Record<ErrorType, ErrorTypeMeta> = {
  맞춤법: { code: "맞춤법", label: "맞춤법", category: "표기", color: "#5b8bff" },
  띄어쓰기: { code: "띄어쓰기", label: "띄어쓰기", category: "표기", color: "#5b8bff" },
  약어오기: { code: "약어오기", label: "약어오기", category: "표기", color: "#5b8bff" },
  문법비문: { code: "문법비문", label: "문법비문", category: "문장", color: "#9a8cf0" },
  선택지누락: { code: "선택지누락", label: "선택지누락", category: "선택지", color: "#ffdb13" },
  선택지중복: { code: "선택지중복", label: "선택지중복", category: "선택지", color: "#ffdb13" },
  용어오류: { code: "용어오류", label: "용어오류", category: "내용", color: "#3ecf8e" },
  사실오류: { code: "사실오류", label: "사실오류", category: "내용", color: "#3ecf8e" },
  정답유출: { code: "정답유출", label: "정답유출", category: "치명", color: "#f5503c" },
  편집표시: { code: "편집표시", label: "편집표시", category: "치명", color: "#f5503c" },
  기타: { code: "기타", label: "기타", category: "기타", color: "#8f8f8f" },
};

/** 안정된 표시 순서 (매트릭스 컬럼 / 반복용). */
export const ERROR_TYPE_ORDER = Object.keys(ERROR_TYPES) as ErrorType[];

export function errorTypeMeta(code: string): ErrorTypeMeta {
  return (
    ERROR_TYPES[code as ErrorType] ?? {
      code: "기타",
      label: code || "기타",
      category: "기타",
      color: "#8f8f8f",
    }
  );
}

/**
 * 병렬 처리 에이전트(논리 레인) 표시 메타. 동시에 도는 워커를 agentA/B/C 로 식별한다.
 * 색은 상태색(found=emerald, error=tomato)과 겹치지 않게 blue/violet/amber 로.
 */
export const AGENT_META: { label: string; color: string }[] = [
  { label: "agentA", color: "#5b8bff" },
  { label: "agentB", color: "#9a8cf0" },
  { label: "agentC", color: "#e0a83e" },
];

export function agentMeta(lane: number): { label: string; color: string } {
  return AGENT_META[lane] ?? { label: `agent${lane}`, color: "#8f8f8f" };
}

/** 신뢰도 표시 메타 (값 자체가 한글 라벨). */
export const CONFIDENCE_META: Record<Confidence, { label: string; tone: string }> = {
  높음: { label: "높음", tone: "--status-found" },
  보통: { label: "보통", tone: "--layer-2" },
  낮음: { label: "낮음", tone: "--muted-foreground" },
};

export const STATUS_META: Record<
  SessionStatus,
  { label: string; tone: "neutral" | "active" | "done" | "error" }
> = {
  uploading: { label: "업로드 중", tone: "neutral" },
  parsing: { label: "파싱 중", tone: "active" },
  running: { label: "분석 중", tone: "active" },
  done: { label: "완료", tone: "done" },
  error: { label: "오류", tone: "error" },
};

export const REVIEW_META: Record<
  ReviewActionType,
  { label: string; varName: string }
> = {
  confirmed: { label: "확인", varName: "--status-found" },
  rejected: { label: "반려", varName: "--status-error" },
  pending: { label: "보류", varName: "--status-hold" },
};
