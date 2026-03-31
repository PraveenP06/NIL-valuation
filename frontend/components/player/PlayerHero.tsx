import Link from "next/link";
import { NilValueBadge } from "@/components/shared/NilValueBadge";
import { ComparisonIndicator } from "@/components/shared/ComparisonIndicator";
import { PositionBadge } from "@/components/shared/PositionBadge";
import { MultiplierPills } from "./MultiplierPills";
import { schoolHref, classYearLabel, conferenceColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PlayerValuation } from "@/lib/types";

type Props = { valuation: PlayerValuation };

export function PlayerHero({ valuation: v }: Props) {
  const bestPublic = v.public_valuations[0]?.nil_value ?? null;

  return (
    <div className="rounded-xl border bg-card p-6 md:p-8">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
        {/* Left: player info */}
        <div className="space-y-3">
          <h1 className="text-3xl md:text-4xl font-bold">{v.name}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <PositionBadge position={v.position} />
            {v.school && (
              <Link href={schoolHref(v.school)} className="text-sm hover:underline font-medium">
                {v.school}
              </Link>
            )}
            {v.conference && (
              <span className={cn("inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium", conferenceColor(v.conference))}>
                {v.conference}
              </span>
            )}
            <span className="text-sm text-muted-foreground">
              {classYearLabel(v.class_year)}
            </span>
          </div>
        </div>

        {/* Right: NIL value + comparison */}
        <div className="space-y-2 md:text-right">
          <NilValueBadge value={v.nil_value} size="lg" highlight />
          <div className="md:flex md:justify-end">
            <ComparisonIndicator ourValue={v.nil_value} publicValue={bestPublic} size="md" />
          </div>
          <MultiplierPills
            position={v.position}
            positionMult={v.position_mult}
            conference={v.conference}
            conferenceMult={v.conference_mult}
          />
        </div>
      </div>
    </div>
  );
}
