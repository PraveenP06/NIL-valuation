import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { PositionBadge } from "@/components/shared/PositionBadge";
import { classYearLabel } from "@/lib/format";
import type { SearchPlayer } from "@/lib/types";

type Props = { player: SearchPlayer };

export function SearchResultCard({ player }: Props) {
  return (
    <Link
      href={`/players/${player.id}`}
      className="flex items-center justify-between rounded-lg border border-border/80 bg-card p-4 hover:bg-accent/40 hover:border-primary/30 transition-all group"
    >
      <div className="flex items-center gap-3">
        <PositionBadge position={player.position} />
        <div className="space-y-0.5">
          <p className="font-medium text-foreground group-hover:text-primary transition-colors">{player.name}</p>
          <p className="text-xs text-muted-foreground">
            {player.school ?? "—"} · {classYearLabel(player.class_year)}
          </p>
        </div>
      </div>
      <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
    </Link>
  );
}
