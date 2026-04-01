import { PlayerTableRow } from "./PlayerTableRow";
import type { LeaderboardPlayer } from "@/lib/types";

type Props = {
  players: LeaderboardPlayer[];
  offset: number;
};

export function PlayerTable({ players, offset }: Props) {
  if (players.length === 0) return null;

  return (
    <div className="rounded-xl border border-border/80 overflow-hidden card-glow">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/80 bg-muted/30">
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider w-12">#</th>
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider">Player</th>
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider hidden md:table-cell">Pos</th>
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider hidden md:table-cell">School</th>
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider hidden lg:table-cell">Conference</th>
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider hidden lg:table-cell">Year</th>
            <th className="px-4 py-3 text-right text-xs text-muted-foreground font-medium uppercase tracking-wider">NIL Value</th>
            <th className="px-4 py-3 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider hidden sm:table-cell">vs Public</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {players.map((player, i) => (
            <PlayerTableRow
              key={player.player_id}
              player={player}
              rank={offset + i + 1}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
