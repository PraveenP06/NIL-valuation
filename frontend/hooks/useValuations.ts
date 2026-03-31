import { useQuery } from "@tanstack/react-query";
import { fetchValuations } from "@/lib/api";
import type { ValuationFilters } from "@/lib/types";

export function useValuations(filters: ValuationFilters) {
  return useQuery({
    queryKey: ["valuations", filters],
    queryFn: () => fetchValuations(filters),
    staleTime: 5 * 60 * 1000,
  });
}
