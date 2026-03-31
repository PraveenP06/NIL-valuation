import { PlayerTableRow } from "./PlayerTableRow";
import type { LeaderboardPlayer } from "@/lib/types";

type Props = {
  players: LeaderboardPlayer[];
  offset: number;
};

export function PlayerTable({ players, offset }: Props) {
  if (players.length === 0) return null;

  return (
    <div className="rounded-lg border overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="border-b">
            <th className="px-4 py-3 text-left text-muted-foreground font-medium w-12">#</th>
            <th className="px-4 py-3 text-left text-muted-foreground font-medium">Name</th>
            <th className="px-4 py-3 text-left text-muted-foreground font-medium hidden md:table-cell">Pos</th>
            <th className="px-4 py-3 text-left text-muted-foreground font-medium hidden md:table-cell">School</th>
            <th className="px-4 py-3 text-left text-muted-foreground font-medium hidden lg:table-cell">Conference</th>
            <th className="px-4 py-3 text-left text-muted-foreground font-medium hidden lg:table-cell">Year</th>
            <th className="px-4 py-3 text-right text-muted-foreground font-medium">NIL Value</th>
            <th className="px-4 py-3 text-left text-muted-foreground font-medium hidden sm:table-cell">vs Public</th>
          </tr>
        </thead>
        <tbody>
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
