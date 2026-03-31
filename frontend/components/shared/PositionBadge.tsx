import { positionColor } from "@/lib/format";
import { cn } from "@/lib/utils";

type Props = {
  position: string | null;
};

export function PositionBadge({ position }: Props) {
  if (!position) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        positionColor(position)
      )}
    >
      {position}
    </span>
  );
}
