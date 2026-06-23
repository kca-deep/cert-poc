/**
 * Mock fixtures — webapp_frontend_plan.md §5 step 2.
 * Three sessions: done-with-findings / done-clean / running.
 *
 * All question text is SYNTHETIC (memory: feedback_generic_prompts) — it must
 * not reproduce real exam items. It only needs to exercise the dashboard UI.
 */

import type {
  Finding,
  Question,
  Session,
  SessionDetail,
} from "../types";

/* ------------------------------------------------------------------ */
/* Session 1 — 완료, 오류 다수                                          */
/* ------------------------------------------------------------------ */

const S1_QUESTIONS: Question[] = [
  {
    qNumber: 1,
    mdText:
      "정보보호의 3대 요소(CIA)에 해당하지 않는 것은?\n\n① 기밀성(Confidentiality)\n② 무결성(Integrity)\n③ 가용성(Availability)\n④ 가용성(Availability)",
  },
  {
    qNumber: 2,
    mdText:
      "다음 중 대칭키 암호 알고리즘으로 옳바른 것은?\n\n① RSA\n② AES\n③ ECC\n④ Diffie-Hellman",
  },
  {
    qNumber: 3,
    mdText:
      "「개인정보보호법」상 개인정보처리자가 정보주체의 동의 없이 개인정보를 수집할 수 있는 경우가 아닌 것은?\n\n① 법률에 특별한 규정이 있는 경우\n② 정보주체와의 계약 이행을 위하여 불가피한 경우\n③ 정보주체의 사전 동의를 받기 곤란한 경우로서 명백히 정보주체의 이익을 위하여 필요한 경우\n④ 처리자의 마케팅 활동을 위하여 필요한 경우",
  },
  {
    qNumber: 4,
    mdText:
      "다음 빈칸에 들어갈 용어로 가장 적절한 것은?\n\n공격자가 정상 사용자의 세션 식별자를 탈취하여 권한을 획득하는 공격을 (    )(이)라 한다.\n\n① 세션 하이재킹\n② 버퍼 오버플로우\n③ SQL 인젝션\n④ 크로스사이트 스크립팅",
  },
  {
    qNumber: 5,
    mdText:
      "해시 함수가 가져야 할 특성으로 옳지 않은 것은?\n\n① 역상 저항성\n② 제2 역상 저항성\n③ 충돌 저항성\n④ 가역성",
  },
  {
    qNumber: 6,
    mdText:
      "다음 중 「정보통신망 이용촉진 및 정보보호등에 관한 법률」 제48조에서 금지하는 행위는?\n\n① 정당한 접근권한 없이 정보통신망에 침입하는 행위\n② 보안 취약점을 신고하는 행위\n③ 백신 프로그램을 배포하는 행위\n④ 방화벽을 설치하는 행위",
  },
  {
    qNumber: 7,
    mdText:
      "위험 관리 절차를 순서대로 바르게 나열한 것은?\n\n① 위험 평가 → 위험 식별 → 위험 대응 → 모니터링\n② 위험 식별 → 위험 평가 → 위험 대응 → 모니터링\n③ 위험 대응 → 위험 식별 → 위험 평가 → 모니터링\n④ 위험 식별 → 위험 대응 → 위험 평가 → 모니터링",
  },
  {
    qNumber: 8,
    mdText:
      "다음 중 DDoS 공격에 대한 대응 방안으로 가장 거리가 먼 것은?\n\n① 트래픽 임계치 기반 탐지\n② CDN 및 스크러빙 센터 활용\n③ 모든 외부 트래픽의 영구 차단\n④ 비정상 트래픽 패턴 분석",
  },
];

const S1_FINDINGS: Finding[] = [
  {
    id: "1-0",
    qNumber: 1,
    location: "보기 ④",
    quote: "④ 가용성(Availability)",
    errorType: "선택지중복",
    reason: "③번과 ④번 보기가 '가용성(Availability)'으로 동일합니다.",
    suggestion: "④ 부인방지(Non-repudiation)",
    confidence: "높음",
  },
  {
    id: "2-0",
    qNumber: 2,
    location: "발문",
    quote: "옳바른 것은?",
    errorType: "맞춤법",
    reason: "'옳바른'은 맞춤법 오류입니다.",
    suggestion: "올바른 것은?",
    confidence: "높음",
  },
  {
    id: "3-0",
    qNumber: 3,
    location: "발문",
    quote: "「개인정보보호법」",
    errorType: "띄어쓰기",
    reason: "법령명 표기상 띄어쓰기 확인이 필요합니다.",
    suggestion: "「개인정보 보호법」",
    confidence: "보통",
  },
  {
    id: "5-0",
    qNumber: 5,
    location: "보기 ④",
    quote: "④ 가역성",
    errorType: "용어오류",
    reason: "해시 함수 특성 맥락에서 '가역성' 용어 사용이 어색합니다.",
    suggestion: "비가역성",
    confidence: "낮음",
  },
  {
    id: "6-0",
    qNumber: 6,
    location: "발문",
    quote: "정보통신망 이용촉진 및 정보보호등에 관한 법률",
    errorType: "띄어쓰기",
    reason: "법령명 '정보보호등'의 '등'을 띄어 써야 합니다.",
    suggestion: "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    confidence: "높음",
  },
];

/* ------------------------------------------------------------------ */
/* Session 2 — 완료, 정상(무탐지)                                       */
/* ------------------------------------------------------------------ */

const S2_QUESTIONS: Question[] = [
  {
    qNumber: 1,
    mdText:
      "방화벽의 기본 정책 중 화이트리스트 방식에 대한 설명으로 옳은 것은?\n\n① 명시적으로 허용된 트래픽만 통과시킨다\n② 명시적으로 차단된 트래픽만 막는다\n③ 모든 트래픽을 통과시킨다\n④ 모든 트래픽을 차단한다",
  },
  {
    qNumber: 2,
    mdText:
      "공개키 기반구조(PKI)에서 인증서를 발급하는 주체는?\n\n① RA\n② CA\n③ VA\n④ CRL",
  },
  {
    qNumber: 3,
    mdText:
      "다음 중 사회공학적 공격에 해당하는 것은?\n\n① 피싱\n② 포트 스캐닝\n③ 무차별 대입\n④ 중간자 공격",
  },
];

/* ------------------------------------------------------------------ */
/* Session 3 — 진행 중                                                  */
/* ------------------------------------------------------------------ */

const S3_QUESTIONS: Question[] = Array.from({ length: 25 }, (_, i) => ({
  qNumber: i + 1,
  mdText: `문항 ${i + 1} 분석 대기 중…`,
}));

const S3_FINDINGS: Finding[] = [
  {
    id: "2-0",
    qNumber: 2,
    location: "발문",
    quote: "할수있다",
    errorType: "띄어쓰기",
    reason: "'할수있다'는 '할 수 있다'로 띄어 써야 합니다.",
    suggestion: "할 수 있다",
    confidence: "보통",
  },
];

/* ------------------------------------------------------------------ */

export const SESSIONS: Session[] = [
  {
    id: "s1",
    createdAt: "2026-05-31T09:12:00+09:00",
    originalFilename: "정보보호개론_2026_1차.hwp",
    fileType: "hwp",
    status: "done",
    questionCount: S1_QUESTIONS.length,
    foundCount: S1_FINDINGS.length,
    elapsedSeconds: 184,
  },
  {
    id: "s2",
    createdAt: "2026-05-30T14:40:00+09:00",
    originalFilename: "정보보호윤리_샘플.hwpx",
    fileType: "hwpx",
    status: "done",
    questionCount: S2_QUESTIONS.length,
    foundCount: 0,
    elapsedSeconds: 92,
  },
  {
    id: "s3",
    createdAt: "2026-06-01T08:55:00+09:00",
    originalFilename: "정보보안기사_실기_v2.pdf",
    fileType: "pdf",
    status: "running",
    questionCount: S3_QUESTIONS.length,
    foundCount: S3_FINDINGS.length,
    elapsedSeconds: 47,
  },
];

const DETAILS: Record<string, SessionDetail> = {
  s1: { session: SESSIONS[0], questions: S1_QUESTIONS, findings: S1_FINDINGS },
  s2: { session: SESSIONS[1], questions: S2_QUESTIONS, findings: [] },
  s3: { session: SESSIONS[2], questions: S3_QUESTIONS, findings: S3_FINDINGS },
};

/**
 * Sessions created at runtime via the upload flow (mock startAnalysis).
 * Kept in-memory only — they vanish on full reload, which is fine for the
 * mock; the real backend (step 8) persists them.
 */
const RUNTIME_SESSIONS: Session[] = [];
const RUNTIME_DETAILS: Record<string, SessionDetail> = {};

export function getMockSessions(): Session[] {
  // Newest runtime sessions first, then the seeded fixtures.
  return [...RUNTIME_SESSIONS, ...SESSIONS];
}

export function getMockSessionDetail(id: string): SessionDetail | null {
  return RUNTIME_DETAILS[id] ?? DETAILS[id] ?? null;
}

/** Register a freshly-started analysis session (status: running). */
export function addMockSession(detail: SessionDetail): void {
  RUNTIME_SESSIONS.unshift(detail.session);
  RUNTIME_DETAILS[detail.session.id] = detail;
}

/**
 * Remove a session and its detail from both the runtime store and the seeded
 * fixtures, so the mock list mirrors a real cascade delete.
 */
export function deleteMockSession(id: string): void {
  const ri = RUNTIME_SESSIONS.findIndex((s) => s.id === id);
  if (ri >= 0) RUNTIME_SESSIONS.splice(ri, 1);
  delete RUNTIME_DETAILS[id];

  const si = SESSIONS.findIndex((s) => s.id === id);
  if (si >= 0) SESSIONS.splice(si, 1);
  delete DETAILS[id];
}

/** A small rotation of synthetic findings to attach on completion. */
const SYNTH_FINDINGS: Omit<Finding, "id" | "qNumber">[] = [
  {
    location: "발문",
    quote: "옳바른",
    errorType: "맞춤법",
    reason: "'옳바른'은 맞춤법 오류입니다.",
    suggestion: "올바른",
    confidence: "높음",
  },
  {
    location: "보기 ④",
    quote: "④ 보기 내용",
    errorType: "선택지중복",
    reason: "③번과 ④번 보기가 동일합니다.",
    suggestion: "보기 내용을 서로 다르게 수정",
    confidence: "높음",
  },
  {
    location: "발문",
    quote: "할수있다",
    errorType: "띄어쓰기",
    reason: "'할수있다'는 '할 수 있다'로 띄어 써야 합니다.",
    suggestion: "할 수 있다",
    confidence: "보통",
  },
  {
    location: "지문",
    quote: "문장이 매끄럽지 않은 부분",
    errorType: "문법비문",
    reason: "문장 구조가 어색해 다듬기가 필요합니다.",
    suggestion: "문장을 자연스럽게 수정",
    confidence: "낮음",
  },
];

/**
 * Transition a runtime session to `done`, synthesising `foundCount` findings
 * spread across its questions. Mirrors what the backend pipeline would persist.
 */
export function completeMockSession(
  id: string,
  foundCount: number,
  elapsedSeconds: number
): void {
  const detail = RUNTIME_DETAILS[id];
  if (!detail) return;

  const qs = detail.questions;
  const n = Math.min(foundCount, qs.length);
  const findings: Finding[] = Array.from({ length: n }, (_, i) => ({
    id: `${qs[i].qNumber}-0`,
    qNumber: qs[i].qNumber,
    ...SYNTH_FINDINGS[i % SYNTH_FINDINGS.length],
  }));

  const updated: Session = {
    ...detail.session,
    status: "done",
    foundCount: n,
    elapsedSeconds,
  };
  RUNTIME_DETAILS[id] = { ...detail, session: updated, findings };

  const idx = RUNTIME_SESSIONS.findIndex((s) => s.id === id);
  if (idx >= 0) RUNTIME_SESSIONS[idx] = updated;
}
