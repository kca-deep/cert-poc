import { errorTypeMeta } from "@/lib/constants";
import type { ErrorType } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Small error-type chip — colored dot + 한글 유형명. 색은 errorTypeMeta 의 카테고리 색. */
export function ErrorTypeChip({
  errorType,
  className,
}: {
  errorType: ErrorType;
  className?: string;
}) {
  const meta = errorTypeMeta(errorType);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-border bg-secondary/40 px-2 py-0.5 text-[13px] font-medium text-foreground/90",
        className
      )}
      title={`${meta.label} (${meta.category})`}
    >
      <span
        className="size-2 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
    </span>
  );
}
