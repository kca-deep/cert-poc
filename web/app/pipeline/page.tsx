import type { Metadata } from "next";

import { PipelineGuide } from "@/components/pipeline/PipelineGuide";

export const metadata: Metadata = {
  title: "파이프라인 상세설명 — CertQA",
  description:
    "윤문 분석 파이프라인의 전체 흐름(업로드→파싱→공급자→검사 L0/L1/L2→후처리→검수)과 검사 단계별 검출 유형 설명",
};

export default function PipelinePage() {
  return <PipelineGuide />;
}
