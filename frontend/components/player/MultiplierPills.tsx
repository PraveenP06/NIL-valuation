import { positionColor, conferenceColor, formatMultiplier } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Multiplier } from "@/lib/types";

type Props = {
  position: string | null;
  positionMult: Multiplier | null;
  conference: string | null;
  conferenceMult: Multiplier | null;
};

export function MultiplierPills({ position, positionMult, conference, conferenceMult }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {position && (
        <span className={cn("inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold", positionColor(position))}>
          {position} {formatMultiplier(positionMult)}
        </span>
      )}
      {conference && (
        <span className={cn("inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold", conferenceColor(conference))}>
          {conference} {formatMultiplier(conferenceMult)}
        </span>
      )}
    </div>
  );
}
