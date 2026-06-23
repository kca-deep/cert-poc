/**
 * PipelineGuide — 현재 프로덕션 윤문 분석 파이프라인 상세설명(정적 문서).
 *
 * 업로드 → 파싱 → 공급자 결정 → holistic 검출(문항당 LLM 1콜) → 결과·검수의 전체
 * 흐름을 설명한다. holistic 전환으로 레이어/규칙·그룹·per-type 구분과 후처리 필터
 * 개념을 폐기했다 — 문항 텍스트 전체를 한 번에 검토해 오류(finding)를 직접 보고한다.
 *
 * 정의 출처(표류 방지):
 *   - 검출 로직:   src/core/pipeline.py (run_pipeline)
 *   - 출력 계약:   prompts/_shared/output_schema.json (Finding · error_type 11-enum)
 *   - 유형 카탈로그: web/lib/constants.ts (ERROR_TYPES)
 *
 * 데이터 fetch 없는 서버 컴포넌트. 다크 전용(Supabase Studio 컨셉).
 */

import { ERROR_TYPE_ORDER, errorTypeMeta } from "@/lib/constants";
import type { ErrorType } from "@/lib/types";

// ── 유형 칩 ───────────────────────────────────────────────────────────────────
function TypeChip({ code }: { code: ErrorType }) {
  const m = errorTypeMeta(code);
  return (
    <span className="inline-flex items-center gap-1 rounded border border-border bg-secondary/40 px-1.5 py-0.5 text-[11px] text-foreground/90">
      <span
        className="size-1.5 rounded-full"
        style={{ backgroundColor: m.color }}
      />
      {m.label}
    </span>
  );
}

// 카테고리별로 유형을 묶어 색 의미를 함께 보여준다.
const CATEGORY_ORDER = ["표기", "문장", "선택지", "내용", "치명", "기타"];
const BY_CATEGORY: { category: string; codes: ErrorType[] }[] =
  CATEGORY_ORDER.map((category) => ({
    category,
    codes: ERROR_TYPE_ORDER.filter(
      (c) => errorTypeMeta(c).category === category
    ),
  })).filter((g) => g.codes.length > 0);

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

function DetailCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-secondary/30 p-3">
      <p className="mb-1 text-[12px] font-medium text-foreground">{title}</p>
      <p className="text-[12px] leading-relaxed text-muted-foreground">
        {children}
      </p>
    </div>
  );
}

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
          시험지 한 부가 업로드부터 검수 확정까지 거치는 전 과정입니다. 각 문항을
          AI가 한 번에 통째로 검토(holistic)해, 발견한 오류를 위치·원문·이유·수정안
          단위로 직접 보고합니다.
        </p>
        {/* 흐름 한눈에 */}
        <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
          {["업로드", "파싱", "공급자 결정", "문항별 검출", "결과·검수"].map(
            (s, i, arr) => (
              <span key={s} className="flex items-center gap-1.5">
                <span className="rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-foreground/90">
                  {s}
                </span>
                {i < arr.length - 1 && (
                  <span className="text-muted-foreground">→</span>
                )}
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
          폐쇄망 기본은 <strong className="font-medium text-foreground">로컬
          gemma4(llama.cpp)</strong> 이며, 필요 시 Claude Haiku(외부망)도 선택할 수
          있습니다. 후보 엔드포인트를 자동탐지해 살아있는 서버·실제 모델을 채택하고,
          <strong className="font-medium text-foreground">
            {" "}
            분석 전에 서버 가용성을 먼저 확인
          </strong>
          해 응답이 없으면 분석을 시작하지 않습니다(빈 세션 방지).
        </Section>

        {/* 3. 문항별 검출 (holistic) */}
        <Section step="3" title="문항별 검출 (holistic — 문항당 LLM 1콜 · 병렬)">
          예전의 규칙/그룹/유형별 다단계 검사를 폐기하고, 문항 텍스트 전체를 한
          번의 호출로 검토합니다. AI는 발견한 오류마다{" "}
          <strong className="font-medium text-foreground">
            위치 · 원문 인용 · 유형 · 이유 · 수정안 · 신뢰도
          </strong>
          를 갖춘 항목(finding)을 직접 만들어 반환합니다. 한 문항에서 여러 오류가
          나올 수 있고, 없으면 빈 결과가 됩니다.
          <div className="mt-3 rounded-md border border-border bg-secondary/30 p-3 text-[12px] leading-relaxed">
            <p className="mb-1 font-medium text-foreground">병렬 처리 · 출력 강제</p>
            문항은 <strong className="text-foreground">동시에 3개</strong>씩
            처리됩니다 — 진행 화면에서 <span style={{ color: "#5b8bff" }}>agentA</span>
            {" · "}
            <span style={{ color: "#9a8cf0" }}>agentB</span>
            {" · "}
            <span style={{ color: "#e0a83e" }}>agentC</span> 세 레인으로 표시되며,
            각 에이전트가 지금 몇 번 문항을 보는지 실시간으로 보입니다(완료 순서는
            문항 난도에 따라 뒤섞일 수 있습니다). 출력은 서버의{" "}
            <strong className="text-foreground">native grammar(JSON 스키마 강제)</strong>
            로 형식이 보장되어, 형식 붕괴 없이 11종 유형 중 하나로 분류됩니다.
          </div>
          <div className="mt-4 flex flex-col gap-2.5">
            {BY_CATEGORY.map((g) => (
              <div key={g.category} className="flex flex-wrap items-center gap-1.5">
                <span className="w-12 shrink-0 text-[11px] text-muted-foreground">
                  {g.category}
                </span>
                {g.codes.map((c) => (
                  <TypeChip key={c} code={c} />
                ))}
              </div>
            ))}
          </div>
          <p className="mt-3 text-[12px] text-muted-foreground">
            신뢰도는 높음 · 보통 · 낮음 세 단계로 표기되어, 검수자가 우선순위를
            판단할 수 있습니다.
          </p>
        </Section>

        {/* 4. 결과 & 검수 */}
        <Section step="4" title="결과 영속화 & 검수">
          탐지된 finding 만 저장합니다. 검수자는 각 항목을
          <strong className="font-medium text-foreground">
            {" "}
            확인 · 반려 · 보류
          </strong>
          로 확정하고, 결과를 검증결과 파일(xlsx·pdf)로 내보낼 수 있습니다.
        </Section>

        {/* 기술 상세 */}
        <section className="rounded-lg border border-border bg-card p-5">
          <h2 className="mb-1 text-[15px] font-medium text-foreground">
            기술 상세
          </h2>
          <p className="mb-4 text-[12px] text-muted-foreground">
            안정적인 검출을 위해 내부에서 동작하는 장치들입니다.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <DetailCard title="입력 정제 (sanitize)">
              일부 로컬 모델이 ‘&gt;’ 마크다운 블록쿼트에서 오작동(무한 추론·깨진
              출력)하므로, 지문 인용 기호를 ‘(지문)’으로 안전하게 치환합니다.
            </DetailCard>
            <DetailCard title="공급자 자동탐지 & 사전 점검">
              설정된 로컬 엔드포인트를 순서대로 health 체크해 살아있는 서버와 그
              서버가 보고하는 실제 모델을 자동 채택합니다. 전부 응답이 없으면
              분석을 시작하지 않습니다.
            </DetailCard>
            <DetailCard title="KV 캐시 격리">
              문항 사이에 캐시가 섞여 검출이 오염되지 않도록, 프롬프트 캐시를 끄고
              서버 슬롯을 분산해 매 호출을 독립적으로 처리합니다.
            </DetailCard>
            <DetailCard title="출력 강제 (native grammar)">
              출력 스키마를 서버의 GBNF grammar 로 변환해 생성 단계에서 형식을
              강제합니다(11종 error_type 중 하나). grammar 미지원 공급자는 관용
              파서로 폴백해 결과 조회가 실패하지 않도록 막습니다.
            </DetailCard>
            <DetailCard title="안정 운영조건">
              결정성을 위해 temperature=0, 추론 폭주를 막기 위해 서버 추론예산
              상한(reasoning-budget)과 충분한 출력 토큰을 적용해 전 문항이 잘림 없이
              완주하도록 합니다.
            </DetailCard>
            <DetailCard title="실시간 진행 (SSE · 병렬)">
              문항 이벤트(start · q_start · q_done · done)를 실시간 스트리밍합니다.
              q_start로 어느 <strong className="text-foreground">agent(A·B·C)</strong>가
              어느 문항을 처리 중인지 즉시 표시되고, 완료된 문항은 탐지 내용이 바로
              채워집니다. 화면을 다시 열어도 진행과 탐지가 처음부터 재생됩니다.
            </DetailCard>
            <DetailCard title="증분 영속 (중간결과 유지)">
              문항이 끝날 때마다 그 결과를 즉시 저장합니다. 분석 도중 진행 화면에서
              문항을 클릭하면 탐지 내용을 바로 볼 수 있고, 새로고침해도 중간결과가
              유지됩니다. 검수(확인·반려·보류)도 분석 중 그 자리에서 가능합니다.
            </DetailCard>
          </div>
        </section>

        {/* 출처 각주 */}
        <p className="px-1 text-[11px] leading-relaxed text-muted-foreground">
          정의 출처 — 검출 로직:{" "}
          <code className="font-mono">src/core/pipeline.py</code>, 출력 계약:{" "}
          <code className="font-mono">prompts/_shared/output_schema.json</code>,
          유형 카탈로그:{" "}
          <code className="font-mono">web/lib/constants.ts</code>. 차수마다 문항은
          바뀌므로 이 문서는 특정 차수 데이터가 아닌 ‘방식’만 설명합니다.
        </p>
      </div>
    </div>
  );
}
