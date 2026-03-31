import { useQuery } from "@tanstack/react-query";
import { fetchSchoolTop } from "@/lib/api";
import type { Season } from "@/lib/types";

export function useSchoolTop(school: string, season: Season) {
  return useQuery({
    queryKey: ["school-top", school, season],
    queryFn: () => fetchSchoolTop(school, season),
    staleTime: 10 * 60 * 1000,
    enabled: school.length > 0,
  });
}
