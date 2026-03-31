import Link from "next/link";
import { NilValueBadge } from "@/components/shared/NilValueBadge";
import { PositionBadge } from "@/components/shared/PositionBadge";
import { ComparisonIndicator } from "@/components/shared/ComparisonIndicator";
import { schoolHref, classYearLabel } from "@/lib/format";
import type { LeaderboardPlayer } from "@/lib/types";

type Props = {
  player: LeaderboardPlayer;
  rank: number;
};

export function PlayerTableRow({ player, rank }: Props) {
  return (
    <tr className="border-b hover:bg-muted/50 transition-colors">
      <td className="px-4 py-3 text-sm text-muted-foreground tabular-nums">{rank}</td>
      <td className="px-4 py-3">
        <Link
          href={`/players/${player.player_id}`}
          className="font-medium hover:underline underline-offset-2"
        >
          {player.name}
        </Link>
      </td>
      <td className="px-4 py-3 hidden md:table-cell">
        <PositionBadge position={player.position} />
      </td>
      <td className="px-4 py-3 hidden md:table-cell">
        <Link href={schoolHref(player.school)} className="text-sm hover:underline">
          {player.school ?? "—"}
        </Link>
      </td>
      <td className="px-4 py-3 hidden lg:table-cell text-sm text-muted-foreground">
        {player.conference ?? "—"}
      </td>
      <td className="px-4 py-3 hidden lg:table-cell text-sm text-muted-foreground">
        {classYearLabel(player.class_year)}
      </td>
      <td className="px-4 py-3 text-right">
        <NilValueBadge value={player.nil_value} />
      </td>
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
