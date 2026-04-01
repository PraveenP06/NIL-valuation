import { comparisonDelta, formatNilValue } from "@/lib/format";
import type { NilDollars } from "@/lib/types";

type Props = {
  ourValue: NilDollars;
  publicValue: NilDollars | null;
  size?: "sm" | "md";
};

export function ComparisonIndicator({ ourValue, publicValue, size = "sm" }: Props) {
  if (publicValue == null) return null;

  const { delta, direction } = comparisonDelta(ourValue, publicValue);

  const isGreen = direction === "above" || direction === "match";
  const dotClass = isGreen ? "bg-emerald-400" : "bg-rose-400";
  const textClass = isGreen ? "text-emerald-400" : "text-rose-400";
  const arrow = direction === "above" ? "↑" : direction === "below" ? "↓" : "≈";
  const label =
    direction === "match"
      ? "≈ matches public"
      : `${arrow} ${formatNilValue(delta)} ${direction} public`;

  if (size === "md") {
    return (
      <div className={`flex items-center gap-2 ${textClass}`}>
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotClass}`} />
        <span className="text-sm font-medium">{label}</span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-1.5 ${textClass}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${dotClass} shrink-0`} />
      <span className="text-xs whitespace-nowrap">{label}</span>
    </div>
  );
}
