import Link from "next/link";
import { NilValueBadge } from "@/components/shared/NilValueBadge";
import { PositionBadge } from "@/components/shared/PositionBadge";
import { ComparisonIndicator } from "@/components/shared/ComparisonIndicator";
import { schoolHref, classYearLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { LeaderboardPlayer } from "@/lib/types";

type Props = {
  player: LeaderboardPlayer;
  rank: number;
};

const RANK_MEDALS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export function PlayerTableRow({ player, rank }: Props) {
  const medal = RANK_MEDALS[rank];
  const isTop3 = rank <= 3;

  return (
    <tr
      className={cn(
        "table-row-hover hover:bg-accent/40",
        isTop3 && "bg-primary/5"
      )}
    >
      {/* Rank */}
      <td className="px-4 py-3 tabular-nums">
        {medal ? (
          <span className="text-base">{medal}</span>
        ) : (
          <span className="text-sm text-muted-foreground">{rank}</span>
        )}
      </td>

      {/* Name */}
      <td className="px-4 py-3">
        <Link
          href={`/players/${player.player_id}`}
          className={cn(
            "font-medium hover:underline underline-offset-2 transition-colors",
            isTop3 ? "text-foreground" : "text-foreground/90 hover:text-foreground"
          )}
        >
          {player.name}
        </Link>
      </td>

      {/* Position */}
      <td className="px-4 py-3 hidden md:table-cell">
        <PositionBadge position={player.position} />
      </td>

      {/* School */}
      <td className="px-4 py-3 hidden md:table-cell">
        <Link
          href={schoolHref(player.school)}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors hover:underline"
        >
          {player.school ?? "—"}
        </Link>
      </td>

      {/* Conference */}
      <td className="px-4 py-3 hidden lg:table-cell text-xs text-muted-foreground">
        {player.conference ?? "—"}
      </td>

      {/* Class year */}
      <td className="px-4 py-3 hidden lg:table-cell text-xs text-muted-foreground">
        {classYearLabel(player.class_year)}
      </td>

      {/* NIL Value */}
      <td className="px-4 py-3 text-right">
        <NilValueBadge value={player.nil_value} />
      </td>

      {/* vs Public */}
      <td className="px-4 py-3 hidden sm:table-cell">
        <ComparisonIndicator
          ourValue={player.nil_value}
          publicValue={player.public_nil_value}
          size="sm"
        />
      </td>
    </tr>
  );
}
