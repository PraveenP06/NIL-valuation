import { useQuery } from "@tanstack/react-query";
import { fetchStats } from "@/lib/api";
import type { Season } from "@/lib/types";

export function useStats(season: Season) {
  return useQuery({
    queryKey: ["stats", season],
    queryFn: () => fetchStats(season),
    staleTime: 5 * 60 * 1000,
  });
}
