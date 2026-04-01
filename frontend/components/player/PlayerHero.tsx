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
    <div className="rounded-xl border border-border/80 bg-card overflow-hidden card-glow">
      {/* Gold accent bar */}
      <div className="h-1 bg-gradient-to-r from-primary/40 via-primary to-primary/40" />

      <div className="p-6 md:p-8">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
          {/* Left: player info */}
          <div className="space-y-3">
            <h1 className="font-display text-4xl md:text-5xl font-bold tracking-wide text-foreground">
              {v.name}
            </h1>
            <div className="flex flex-wrap items-center gap-2">
              <PositionBadge position={v.position} />
              {v.school && (
                <Link
                  href={schoolHref(v.school)}
                  className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hover:underline"
                >
                  {v.school}
                </Link>
              )}
              {v.conference && (
                <span
                  className={cn(
                    "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
                    conferenceColor(v.conference)
                  )}
                >
                  {v.conference}
                </span>
              )}
              <span className="text-xs text-muted-foreground bg-muted rounded px-2 py-0.5">
                {classYearLabel(v.class_year)}
              </span>
            </div>
          </div>

          {/* Right: NIL value + comparison */}
          <div className="space-y-2 md:text-right shrink-0">
            <div className="space-y-0.5">
              <p className="text-xs text-muted-foreground uppercase tracking-wider">Model NIL Value</p>
              <NilValueBadge value={v.nil_value} size="lg" highlight />
            </div>
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
    </div>
  );
}
