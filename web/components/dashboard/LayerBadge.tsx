import { LAYER_META } from "@/lib/constants";
import type { Layer } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Small layer chip — colored dot + L0/L1/L2 label (plan §2 color mapping). */
export function LayerBadge({
  layer,
  className,
}: {
  layer: Layer;
  className?: string;
}) {
  const meta = LAYER_META[layer];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-border bg-secondary/40 px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground",
        className
      )}
      title={meta.label}
    >
      <span
        className="size-1.5 rounded-full"
        style={{ backgroundColor: `var(${meta.varName})` }}
      />
      {meta.short}
    </span>
  );
}
