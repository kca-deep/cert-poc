/**
 * PipelineGuide — 현재 프로덕션 윤문 분석 파이프라인 상세설명(정적 문서).
 *
 * 업로드 → 파싱 → 공급자 → 검사(L0/L1/L2) → 후처리 → 결과·검수의 전체 흐름을
 * 설명한다. 레이어별 검사 유형은 web/lib/constants.ts 카탈로그에서 파생하므로
 * (하드코딩 금지) 항상 프로덕션과 일치한다.
 *
 * 정의 출처(표류 방지):
 *   - 레이어/그룹 구성: src/core/pipeline.py (LAYER0_TYPES·LAYER1_GROUPS·LAYER2_TYPES)
 *   - 후처리 필터:      src/postprocess.py (F1~F5)
 *   - 유형 카탈로그:    web/lib/constants.ts (ANOMALY_TYPES)
 *
 * 데이터 fetch 없는 서버 컴포넌트. 다크 전용(Supabase Studio 컨셉).
 */

import {
  ANOMALY_TYPES,
  ANOMALY_TYPE_ORDER,
  LAYER_META,
  type AnomalyTypeMeta,
} from "@/lib/constants";
import type { Layer } from "@/lib/types";
import { LayerBadge } from "@/components/dashboard/LayerBadge";

// ── constants 파생: 레이어별 유형 / L1 그룹별 유형 ───────────────────────────
const BY_LAYER: Record<Layer, AnomalyTypeMeta[]> = { 0: [], 1: [], 2: [] };
for (const code of ANOMALY_TYPE_ORDER) {
  const meta = ANOMALY_TYPES[code];
  BY_LAYER[meta.layer].push(meta);
}

// L1 은 프롬프트 묶음(G1·G4·G5) 단위로 1회 호출 → 그룹별로 다시 묶어 보여준다.
const GROUP_LABEL: Record<string, string> = {
  G1: "맞춤법·표기",
  G4: "법령 도메인",
  G5: "편집·정답노출",
};
const L1_GROUPS: { group: string; label: string; types: AnomalyTypeMeta[] }[] = [];
for (const m of BY_LAYER[1]) {
  const key = m.group ?? "기타";
  let g = L1_GROUPS.find((x) => x.group === key);
  if (!g) {
    g = { group: key, label: GROUP_LABEL[key] ?? key, types: [] };
    L1_GROUPS.push(g);
  }
  g.types.push(m);
}

const LAYER_METHOD: Record<Layer, { method: string; cost: string }> = {
  0: { method: "규칙 · 정규식", cost: "AI 0회" },
  1: { method: "묶음(그룹) LLM", cost: "그룹당 1회" },
  2: { method: "유형별 LLM", cost: "유형당 1회" },
};

const LAYER_NOTE: Record<Layer, string> = {
  0: "기계적으로 판정 가능한 구조 오류는 AI 없이 규칙으로 즉시 검출합니다(비용 0).",
  1: "성격이 비슷한 유형을 한 번의 호출로 묶어 검사해 호출 수를 줄입니다(비용 절감).",
  2: "묶기 어려운 미묘한 유형은 유형별 전용 프롬프트로 1:1 정밀 검사합니다.",
};

// ── 소형 표현 요소 ───────────────────────────────────────────────────────────
function TypeChip({ m }: { m: AnomalyTypeMeta }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-border bg-secondary/40 px-1.5 py-0.5 text-[11px] text-foreground/90">
      <span className="font-mono text-[10px] text-muted-foreground/70">{m.code}</span>
      {m.label}
    </span>
  );
}

function Section({
  step,
  title,
  children,
}: {
  step: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="grid size-5 shrink-0 place-items-center rounded-full bg-secondary font-mono text-[10px] tabular-nums text-muted-foreground">
          {step}
        </span>
        <h2 className="text-[15px] font-medium text-foreground">{title}</h2>
      </div>
      <div className="text-[13px] leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-secondary/30 p-3">
      <p className="mb-1 text-[12px] font-medium text-foreground">{title}</p>
      <p className="text-[12px] leading-relaxed text-muted-foreground">{children}</p>
    </div>
  );
}

// ── 후처리 필터 (출처: src/postprocess.py docstring) ─────────────────────────
const FILTERS: { id: string; text: string }[] = [
  { id: "F1", text: "같은 문항에서 오자(A02)와 띄어쓰기(A06)가 함께 잡히면, 오자를 띄어쓰기로 오분류한 A06을 제거합니다." },
  { id: "F2", text: "낙서형1(A11)과 낙서형2(A12)가 함께 잡히면 중복인 A11을 제거합니다(A12 우선)." },
  { id: "F3", text: "띄어쓰기(A06) 원문에 ‘|’가 있으면 마크다운 표 파싱 아티팩트로 보고 제거합니다." },
  { id: "F4", text: "오자(A02) 근거에 ‘의미상·문맥상·사전에 있는’ 같은 판단 표현이 있으면 사전 등재어 오분류로 제거합니다." },
  { id: "F5", text: "오자(A02)·탈자(A16) 교정 전후 단어가 음절을 전혀 공유하지 않으면, 자모 오타가 아닌 의미 교체로 보고 제거합니다." },
];

// ── 메인 ─────────────────────────────────────────────────────────────────────
export function PipelineGuide() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      {/* Hero */}
      <header className="mb-6">
        <h1 className="text-2xl font-medium tracking-tight text-foreground">
          윤문 분석 파이프라인
        </h1>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
          시험지 한 부가 업로드부터 검수 확정까지 거치는 전 과정입니다. 비싼 AI
          호출을 최소화하려고, 규칙으로 잡을 수 있는 건 규칙으로, 판단이 필요한
          것만 AI로 검사합니다.
        </p>
        {/* 흐름 한눈에 */}
        <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
          {["업로드", "파싱", "공급자 결정", "검사 L0→L1→L2", "후처리", "결과·검수"].map(
            (s, i, arr) => (
              <span key={s} className="flex items-center gap-1.5">
                <span className="rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-foreground/90">
                  {s}
                </span>
                {i < arr.length - 1 && <span className="text-muted-foreground/50">→</span>}
              </span>
            )
          )}
        </div>
      </header>

      <div className="flex flex-col gap-4">
        {/* 1. 업로드 & 파싱 */}
        <Section step="1" title="업로드 & 파싱">
          HWP·HWPX·PDF 문제지를 (kordoc로) 마크다운으로 변환하고, 문항 단위
          <code className="mx-1 rounded bg-secondary px-1 py-0.5 font-mono text-[11px] text-foreground">
            ## N.
          </code>
          로 나눕니다. 이후 단계는 이 문항 텍스트를 입력으로 사용합니다.
        </Section>

        {/* 2. 공급자 결정 */}
        <Section step="2" title="LLM 공급자 결정 (분석 전 점검)">
          로컬 LLM(gpt-oss / exaone 자동탐지) 또는 Claude Haiku 중에서 선택합니다.
          <strong className="font-medium text-foreground"> 분석을 시작하기 전에
          서버가 살아있는지 먼저 확인</strong>하고, 응답이 없으면 분석을 시작하지
          않습니다(빈 세션 방지).
        </Section>

        {/* 3. 검사 단계 — 표를 하위에 */}
        <Section step="3" title="검사 단계 (3레이어 하이브리드)">
          값싼 검사부터 단계적으로 적용해 비용과 정확도를 맞춥니다. 아래 표가 각
          레이어가 무엇을 어떻게 검사하는지 보여줍니다.

          {/* 하위: 레이어별 검사 표 */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground/70">
                  <th className="py-2 pr-3 font-medium">레이어</th>
                  <th className="py-2 pr-3 font-medium">방식</th>
                  <th className="py-2 pr-3 font-medium">비용</th>
                  <th className="py-2 font-medium">검사 유형</th>
                </tr>
              </thead>
              <tbody>
                {([0, 1, 2] as Layer[]).map((layer) => (
                  <tr key={layer} className="border-b border-border/60 align-top">
                    <td className="py-3 pr-3">
                      <LayerBadge layer={layer} />
                    </td>
                    <td className="py-3 pr-3 text-[12px] text-foreground">
                      {LAYER_METHOD[layer].method}
                    </td>
                    <td className="py-3 pr-3 font-mono text-[12px] text-muted-foreground">
                      {LAYER_METHOD[layer].cost}
                    </td>
                    <td className="py-3">
                      {layer === 1 ? (
                        <div className="flex flex-col gap-2">
                          {L1_GROUPS.map((g) => (
                            <div key={g.group} className="flex flex-wrap items-center gap-1.5">
                              <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                                {g.group} {g.label}
                              </span>
                              {g.types.map((m) => (
                                <TypeChip key={m.code} m={m} />
                              ))}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {BY_LAYER[layer].map((m) => (
                            <TypeChip key={m.code} m={m} />
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 레이어별 한 줄 부연 */}
          <ul className="mt-4 flex flex-col gap-1.5 text-[12px]">
            {([0, 1, 2] as Layer[]).map((layer) => (
              <li key={layer} className="flex items-start gap-2">
                <span className="mt-0.5 font-mono text-[10px] text-muted-foreground/70">
                  {LAYER_META[layer].short}
                </span>
                <span className="text-muted-foreground">{LAYER_NOTE[layer]}</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* 4. 후처리 */}
        <Section step="4" title="후처리 (오탐 자동 제거)">
          탐지 결과 중 알려진 오탐 패턴을 자동으로 걸러냅니다. ‘탐지’ 건수와 ‘오탐
          제거’ 건수는 결과 화면에서 분리해 표기합니다.
          <ul className="mt-3 flex flex-col gap-1.5">
            {FILTERS.map((f) => (
              <li key={f.id} className="flex items-start gap-2 text-[12px]">
                <span className="mt-0.5 shrink-0 rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {f.id}
                </span>
                <span className="text-muted-foreground">{f.text}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-muted-foreground/70">
            적용 순서: F3 → F4 → F5 → F1 → F2
          </p>
        </Section>

        {/* 5. 결과 & 검수 */}
        <Section step="5" title="결과 영속화 & 검수">
          탐지되었거나 후처리로 필터된 항목만 저장합니다. 검수자는 각 항목을
          <strong className="font-medium text-foreground"> 확인 · 반려 · 보류</strong>
          로 확정하고, 결과를 검증결과 파일(xlsx·pdf)로 내보낼 수 있습니다.
        </Section>

        {/* 기술 상세 — 접이식 없이 펼쳐서 */}
        <section className="rounded-lg border border-border bg-card p-5">
          <h2 className="mb-1 text-[15px] font-medium text-foreground">기술 상세</h2>
          <p className="mb-4 text-[12px] text-muted-foreground">
            안정적인 검출을 위해 내부에서 동작하는 장치들입니다.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <DetailCard title="입력 정제 (sanitize)">
              일부 로컬 모델이 ‘&gt;’ 마크다운 블록쿼트에서 오작동(무한 추론·깨진
              출력)하므로, 지문 인용 기호를 ‘(지문)’으로 안전하게 치환합니다.
            </DetailCard>
            <DetailCard title="공급자 자동탐지 & 사전 점검">
              설정된 로컬 엔드포인트(예: 8080·8081)를 순서대로 health 체크해 살아있는
              서버와 그 서버가 보고하는 실제 모델을 자동 채택합니다. 전부 응답이 없으면
              분석을 시작하지 않습니다.
            </DetailCard>
            <DetailCard title="KV 캐시 격리">
              문항 사이에 캐시가 섞여 검출이 오염되지 않도록, 프롬프트 캐시를 끄고
              서버 슬롯을 분산해 매 호출을 독립적으로 처리합니다.
            </DetailCard>
            <DetailCard title="결과 정규화">
              AI가 출력 형식을 어겨도(예: 보조정보를 문자열로 반환) 저장 전에 교정해,
              결과 조회가 실패하지 않도록 막습니다.
            </DetailCard>
            <DetailCard title="실시간 진행 (SSE)">
              레이어·문항 단위 진행 이벤트를 실시간 스트리밍하며, 화면을 다시 열어도
              진행 상황을 처음부터 재생합니다.
            </DetailCard>
            <DetailCard title="결과 저장 흐름">
              레이어 결과를 병합(merged) → 후처리 필터(merged_filtered) → 검수용
              테이블에 적재하며, 탐지/필터된 항목만 남깁니다.
            </DetailCard>
          </div>
        </section>

        {/* 출처 각주 */}
        <p className="px-1 text-[11px] leading-relaxed text-muted-foreground/60">
          정의 출처 — 레이어/그룹: <code className="font-mono">src/core/pipeline.py</code>,
          후처리 필터: <code className="font-mono">src/postprocess.py</code>, 유형
          카탈로그: <code className="font-mono">web/lib/constants.ts</code>. 차수마다
          문항은 바뀌므로 이 문서는 특정 차수 데이터가 아닌 ‘방식’만 설명합니다.
        </p>
      </div>
    </div>
  );
}
