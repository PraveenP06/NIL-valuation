import { useQuery } from "@tanstack/react-query";
import { fetchSearch } from "@/lib/api";
import type { Season } from "@/lib/types";

export function useSearch(query: string, season?: Season) {
  return useQuery({
    queryKey: ["search", query, season],
    queryFn: () => fetchSearch(query, season),
    staleTime: 60 * 1000,
    enabled: query.length >= 2,
  });
}
