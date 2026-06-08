import Link from "next/link";
import { BookOpen, ArrowUpRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * PipelineGuideLink — "파이프라인 상세설명" 진입 버튼(새 탭).
 *
 * 새 분석(UploadView) 헤더와 세션 "분석 진행" 카드에서 공통으로 쓰는 트리거.
 * 상태 없는 표현 컴포넌트라 client/server 트리 어디서나 임베드 가능하다.
 */
export function PipelineGuideLink({
  className,
  size = "sm",
}: {
  className?: string;
  size?: "xs" | "sm";
}) {
  return (
    <Button
      asChild
      variant="ghost"
      size={size}
      className={cn("text-muted-foreground", className)}
    >
      <Link href="/pipeline" target="_blank" rel="noopener noreferrer">
        <BookOpen />
        파이프라인 상세설명
        <ArrowUpRight />
      </Link>
    </Button>
  );
}
