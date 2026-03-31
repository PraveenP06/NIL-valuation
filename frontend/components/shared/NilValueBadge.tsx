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
        "font-mono font-semibold tabular-nums",
        size === "lg" ? "text-3xl font-bold" : "text-sm",
        highlight ? "text-emerald-700" : "text-foreground"
      )}
    >
      {formatNilValue(value)}
    </span>
  );
}
