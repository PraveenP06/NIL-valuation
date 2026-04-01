import { formatNilValue } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { NilDollars } from "@/lib/types";

type Props = {
  value: NilDollars | null;
  size?: "sm" | "lg";
  highlight?: boolean;
};

export function NilValueBadge({ value, size = "sm", highlight = false }: Props) {
  return (
    <span
      className={cn(
        "font-mono tabular-nums font-semibold",
        size === "lg" ? "text-3xl font-bold font-display text-primary gold-glow" : "text-sm",
        !highlight && size !== "lg" && "text-amber-400"
      )}
    >
      {formatNilValue(value)}
    </span>
  );
}
