// ─── Primitive aliases ────────────────────────────────────────────────────────
export type Season = number;
export type PlayerId = number;
export type NilDollars = number;
export type Score = number; // 0–100
export type Multiplier = number; // e.g. 0.7–1.5

// ─── Public valuation entry (one source/deal) ─────────────────────────────────
export type PublicValuationEntry = {
  nil_value: NilDollars;
  source: string;
  scraped_at: string;
};

// ─── Leaderboard row ──────────────────────────────────────────────────────────
export type LeaderboardPlayer = {
  player_id: PlayerId;
  season: Season;
  nil_value: NilDollars;
  perf_score: Score | null;
  social_score: Score | null;
  school_score: Score | null;
  class_score: Score | null;
  recruit_score: Score | null;
  collective_score: Score | null;
  position_mult: Multiplier | null;
  conference_mult: Multiplier | null;
  name: string;
  position: string | null;
  school: string | null;
  conference: string | null;
  class_year: number | null;
  public_nil_value: NilDollars | null;
  public_source: string | null;
};

export type ValuationsResponse = {
  data: LeaderboardPlayer[];
  limit: number;
  offset: number;
  season: Season;
};

// ─── Player detail ────────────────────────────────────────────────────────────
export type PlayerValuation = {
  player_id: PlayerId;
  season: Season;
  nil_value: NilDollars;
  perf_score: Score | null;
  social_score: Score | null;
  school_score: Score | null;
  class_score: Score | null;
  recruit_score: Score | null;
  collective_score: Score | null;
  position_mult: Multiplier | null;
  conference_mult: Multiplier | null;
  name: string;
  position: string | null;
  school: string | null;
  conference: string | null;
  class_year: number | null;
  public_valuations: PublicValuationEntry[];
};

// ─── Search ───────────────────────────────────────────────────────────────────
export type SearchPlayer = {
  id: PlayerId;
  name: string;
  position: string | null;
  school: string | null;
  conference: string | null;
  class_year: number | null;
  season: Season;
};

export type SearchResponse = {
  data: SearchPlayer[];
  query: string;
};

// ─── School ───────────────────────────────────────────────────────────────────
export type SchoolTopResponse = {
  school: string;
  season: Season;
  data: Omit<LeaderboardPlayer, "public_nil_value" | "public_source">[];
};

// ─── Filters ──────────────────────────────────────────────────────────────────
export type FilterMeta = {
  positions: string[];
  conferences: string[];
  schools: string[];
};

// ─── Stats ────────────────────────────────────────────────────────────────────
export type SiteStats = {
  season: Season;
  players_count: number;
  valuations_count: number;
  social_data_count: number;
  top_nil_value: NilDollars | null;
};

// ─── Filter params (used by hooks and FilterBar) ─────────────────────────────
export type ValuationFilters = {
  season: Season;
  position: string | null;
  conference: string | null;
  class_year: number | null;
  limit: number;
  offset: number;
};
