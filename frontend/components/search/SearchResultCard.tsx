import Link from "next/link";
import { PositionBadge } from "@/components/shared/PositionBadge";
import { classYearLabel } from "@/lib/format";
import type { SearchPlayer } from "@/lib/types";

type Props = { player: SearchPlayer };

export function SearchResultCard({ player }: Props) {
  return (
    <Link
      href={`/players/${player.id}`}
      className="flex items-center justify-between rounded-lg border bg-card p-4 hover:bg-muted/50 hover:ring-1 hover:ring-primary/20 transition-all"
    >
      <div className="space-y-1">
        <p className="font-medium">{player.name}</p>
        <p className="text-sm text-muted-foreground">
          {player.school ?? "—"} · {classYearLabel(player.class_year)}
        </p>
      </div>
      <PositionBadge position={player.position} />
    </Link>
  );
}
