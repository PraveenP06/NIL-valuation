import { useQuery } from "@tanstack/react-query";
import { fetchPlayerValuation } from "@/lib/api";
import type { PlayerId, Season } from "@/lib/types";

export function usePlayerValuation(playerId: PlayerId | null, season: Season) {
  return useQuery({
    queryKey: ["player-valuation", playerId, season],
    queryFn: () => fetchPlayerValuation(playerId!, season),
    staleTime: 10 * 60 * 1000,
    enabled: playerId != null,
  });
}
