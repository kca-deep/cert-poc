/**
 * Mock parsing — turns an uploaded file into a markdown ParseResult without a
 * backend. For `.md` uploads we read the real text; otherwise we synthesise a
 * plausible question set (synthetic, per memory: feedback_generic_prompts).
 *
 * Replaced by the FastAPI /upload parse step (webapp_plan §5) later.
 */

import type {
  FileType,
  ParseResult,
  ParseWarning,
  Question,
} from "../types";

export function fileTypeOf(filename: string): FileType {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (ext === "hwpx") return "hwpx";
  if (ext === "pdf") return "pdf";
  return "hwp";
}

/** Split a parsed markdown blob into questions by the `## N.` heading. */
function splitMarkdownIntoQuestions(md: string): Question[] {
  const parts = md.split(/(?=^##\s*\d+\.)/m).filter((p) => p.trim());
  return parts.map((block, i) => {
    const m = block.match(/^##\s*(\d+)\./);
    return {
      qNumber: m ? Number(m[1]) : i + 1,
      mdText: block.trim(),
    };
  });
}

const SYNTH_BANK: string[] = [
  "다음 중 정보보호의 기본 목표에 해당하지 않는 것은?\n\n① 기밀성\n② 무결성\n③ 가용성\n④ 확장성",
  "대칭키 암호 알고리즘으로 옳은 것은?\n\n① RSA\n② AES\n③ ECC\n④ ElGamal",
  "다음 빈칸에 들어갈 용어로 가장 적절한 것은?\n\n( )은(는) 정상 사용자의 세션 식별자를 탈취하는 공격이다.\n\n① 세션 하이재킹\n② 버퍼 오버플로우\n③ SQL 인젝션\n④ XSS",
  "「개인정보 보호법」상 동의 없이 개인정보를 수집할 수 있는 경우가 아닌 것은?\n\n① 법률에 규정이 있는 경우\n② 계약 이행에 불가피한 경우\n③ 정보주체의 급박한 생명·신체 보호\n④ 사업자의 마케팅 목적",
  "해시 함수가 가져야 할 특성으로 옳지 않은 것은?\n\n① 역상 저항성\n② 제2 역상 저항성\n③ 충돌 저항성\n④ 가역성",
  "방화벽의 화이트리스트 정책에 대한 설명으로 옳은 것은?\n\n① 허용된 트래픽만 통과\n② 차단된 트래픽만 차단\n③ 모든 트래픽 통과\n④ 모든 트래픽 차단",
];

/** Build a synthetic question list of the given size from the bank. */
function synthQuestions(count: number): Question[] {
  return Array.from({ length: count }, (_, i) => ({
    qNumber: i + 1,
    mdText: `## ${i + 1}.\n\n${SYNTH_BANK[i % SYNTH_BANK.length]}`,
  }));
}

/** Derive a deterministic count from the filename so reloads are stable. */
function deterministicCount(filename: string): number {
  let h = 0;
  for (const ch of filename) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return 12 + (h % 14); // 12–25 questions
}

/** Synthesise pre-analysis sanity-check warnings. */
function buildWarnings(questions: Question[]): ParseWarning[] {
  const warnings: ParseWarning[] = [];
  const n = questions.length;
  if (n === 0) {
    warnings.push({
      severity: "warning",
      message: "문항을 인식하지 못했습니다. '## 번호.' 형식인지 확인하세요.",
    });
    return warnings;
  }
  // Flag any question whose body looks like it is missing a 4th choice.
  for (const q of questions) {
    const choiceCount = (q.mdText.match(/[①②③④⑤]/g) ?? []).length;
    if (choiceCount > 0 && choiceCount < 4) {
      warnings.push({
        qNumber: q.qNumber,
        severity: "warning",
        message: `보기 개수가 ${choiceCount}개로 부족할 수 있습니다 (4개 기대).`,
      });
    }
  }
  warnings.push({
    severity: "info",
    message: `${n}개 문항을 추출했습니다. 본문은 마크다운으로 변환되었습니다.`,
  });
  return warnings.slice(0, 5);
}

export async function mockParse(file: File): Promise<ParseResult> {
  const filename = file.name;
  const fileType = fileTypeOf(filename);
  const isMd = filename.toLowerCase().endsWith(".md");

  let questions: Question[];
  let mergedMd: string;

  if (isMd) {
    const text = await file.text();
    questions = splitMarkdownIntoQuestions(text);
    mergedMd = text;
  } else {
    // Binary formats (hwp/hwpx/pdf) cannot be parsed in the browser — synthesise.
    questions = synthQuestions(deterministicCount(filename));
    mergedMd = questions.map((q) => q.mdText).join("\n\n");
  }

  return {
    filename,
    fileType,
    sizeBytes: file.size,
    questionCount: questions.length,
    questions,
    mergedMd,
    warnings: buildWarnings(questions),
  };
}
