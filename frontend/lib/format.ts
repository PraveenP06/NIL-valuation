import type { NilDollars, Multiplier, Score } from "@/lib/types";

// ─── NIL dollar formatting ────────────────────────────────────────────────────

export function formatNilValue(dollars: NilDollars | null | undefined): string {
  if (dollars == null) return "—";
  if (dollars >= 1_000_000) {
    const val = dollars / 1_000_000;
    return `$${val % 1 === 0 ? val.toFixed(0) : val.toFixed(1)}M`;
  }
  if (dollars >= 10_000) {
    return `$${Math.round(dollars / 1_000)}K`;
  }
  if (dollars >= 1_000) {
    const val = dollars / 1_000;
    return `$${val.toFixed(1)}K`;
  }
  return `$${Math.round(dollars)}`;
}

// ─── Score formatting ─────────────────────────────────────────────────────────

export function formatScore(score: Score | null | undefined): string {
  if (score == null) return "—";
  return String(Math.round(score));
}

// ─── Multiplier formatting ────────────────────────────────────────────────────

export function formatMultiplier(mult: Multiplier | null | undefined): string {
  if (mult == null) return "—";
  return `${mult.toFixed(1)}×`;
}

// ─── Position color (Tailwind classes) ───────────────────────────────────────

export function positionColor(position: string | null): string {
  switch (position) {
    case "QB":
      return "bg-red-100 text-red-800";
    case "WR":
    case "TE":
    case "RB":
      return "bg-orange-100 text-orange-800";
    case "DB":
    case "CB":
    case "S":
    case "SS":
    case "FS":
      return "bg-blue-100 text-blue-800";
    case "DL":
    case "DE":
    case "DT":
    case "LB":
      return "bg-green-100 text-green-800";
    case "OL":
    case "OT":
    case "OG":
    case "C":
      return "bg-yellow-100 text-yellow-800";
    case "K":
    case "P":
      return "bg-gray-100 text-gray-600";
    default:
      return "bg-slate-100 text-slate-700";
  }
}

// ─── Conference color (Tailwind classes) ──────────────────────────────────────

export function conferenceColor(conference: string | null): string {
  switch (conference) {
    case "SEC":
      return "bg-amber-100 text-amber-800";
    case "Big Ten":
      return "bg-indigo-100 text-indigo-800";
    case "ACC":
      return "bg-purple-100 text-purple-800";
    case "Big 12":
      return "bg-teal-100 text-teal-800";
    case "Pac-12":
      return "bg-sky-100 text-sky-800";
    default:
      return "bg-slate-100 text-slate-700";
  }
}

// ─── Comparison delta ─────────────────────────────────────────────────────────

export type ComparisonDelta = {
  delta: NilDollars;
  direction: "above" | "below" | "match";
};

export function comparisonDelta(
  ourValue: NilDollars,
  publicValue: NilDollars
): ComparisonDelta {
  const delta = ourValue - publicValue;
  const pct = Math.abs(delta) / publicValue;
  if (pct < 0.02) return { delta, direction: "match" };
  return { delta: Math.abs(delta), direction: delta >= 0 ? "above" : "below" };
}

// ─── Class year label ─────────────────────────────────────────────────────────

export function classYearLabel(classYear: number | null | undefined): string {
  switch (classYear) {
    case 1:
      return "FR";
    case 2:
      return "SO";
    case 3:
      return "JR";
    case 4:
      return "SR";
    default:
      return "—";
  }
}

// ─── Score key → display label ────────────────────────────────────────────────

export function scoreLabel(key: string): string {
  const labels: Record<string, string> = {
    perf_score: "Performance",
    social_score: "Social",
    school_score: "School",
    class_score: "Class Year",
    recruit_score: "Recruit",
    collective_score: "Collective",
  };
  return labels[key] ?? key;
}

// ─── Source label ─────────────────────────────────────────────────────────────

export function formatSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    on3_rank_estimate: "ON3 Rank Estimate",
    web_2025: "Web (2025)",
    forbes_reported: "Forbes",
  };
  return labels[source] ?? source;
}

// ─── School href (encodes special chars) ──────────────────────────────────────

export function schoolHref(school: string | null): string {
  if (!school) return "#";
  return `/school/${encodeURIComponent(school)}`;
}
