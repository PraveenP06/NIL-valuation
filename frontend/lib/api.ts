import type {
  ValuationsResponse,
  PlayerValuation,
  SchoolTopResponse,
  SearchResponse,
  FilterMeta,
  SiteStats,
  ValuationFilters,
  PlayerId,
  Season,
} from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Error type ───────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, { next: { revalidate: 300 } });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text);
  }
  return res.json() as Promise<T>;
}

// ─── Query string builder (omits null/undefined values) ──────────────────────

function qs(params: Record<string, string | number | null | undefined>): string {
  const parts: string[] = [];
  for (const [key, val] of Object.entries(params)) {
    if (val != null) parts.push(`${key}=${encodeURIComponent(String(val))}`);
  }
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

// ─── API functions ────────────────────────────────────────────────────────────

export function fetchValuations(
  filters: ValuationFilters
): Promise<ValuationsResponse> {
  const q = qs({
    season: filters.season,
    position: filters.position,
    conference: filters.conference,
    class_year: filters.class_year,
    limit: filters.limit,
    offset: filters.offset,
  });
  return apiFetch<ValuationsResponse>(`/api/valuations${q}`);
}

export function fetchPlayerValuation(
  playerId: PlayerId,
  season: Season
): Promise<PlayerValuation> {
  return apiFetch<PlayerValuation>(
    `/api/players/${playerId}/valuation${qs({ season })}`
  );
}

export function fetchSchoolTop(
  school: string,
  season: Season,
  limit = 25
): Promise<SchoolTopResponse> {
  return apiFetch<SchoolTopResponse>(
    `/api/school/${encodeURIComponent(school)}/top${qs({ season, limit })}`
  );
}

export function fetchSearch(
  query: string,
  season?: Season,
  limit = 20
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(
    `/api/players/search${qs({ q: query, season, limit })}`
  );
}

export function fetchFilterMeta(season: Season): Promise<FilterMeta> {
  return apiFetch<FilterMeta>(`/api/filters/meta${qs({ season })}`);
}

export function fetchStats(season: Season): Promise<SiteStats> {
  return apiFetch<SiteStats>(`/api/stats${qs({ season })}`);
}
