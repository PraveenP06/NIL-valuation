import { useQuery } from "@tanstack/react-query";
import { fetchFilterMeta } from "@/lib/api";
import type { Season } from "@/lib/types";

export function useFilterMeta(season: Season) {
  return useQuery({
    queryKey: ["filter-meta", season],
    queryFn: () => fetchFilterMeta(season),
    staleTime: 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  });
}
