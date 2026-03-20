"""
Pull NIL valuations from DuckDuckGo/On3 search results for players in the DB
who already have BOTH performance stats AND social media follower data.

Appends new entries to data/nil_websearch.json (skips players already labeled).

Tier-sampling mode (recommended):
    Loads nil_predictions_calibrated.csv and stratifies eligible players into
    low / mid / high tiers by predicted NIL value, then samples evenly across
    tiers so the training set covers the full dollar range.

Usage:
    # Tier-sampled run — 50 from each tier (recommended)
    python src/db/ingestion/pull_nil_valuations.py --tier-sample 50

    # Raw run — first N eligible players with stats+followers
    python src/db/ingestion/pull_nil_valuations.py --max-players 80 --season 2024
"""
import os
import sys
import re
import json
import time
import random
import argparse

import pandas as pd
from ddgs import DDGS
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client
from dotenv import load_dotenv

load_dotenv()

SEARCH_DELAY = 2.0   # seconds between DuckDuckGo queries
PAGE_SIZE    = 1000
NIL_MAX      = 7_000_000   # Arch Manning ($6.8M) is roughly the college NIL ceiling

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../data'))
WEB_PATH = os.path.join(DATA_DIR, 'nil_websearch.json')
CSV_PATH = os.path.join(DATA_DIR, 'nil_predictions_calibrated.csv')

# Tier boundaries (predicted NIL value in dollars)
LOW_MAX  = 1_400_000   # low  tier: < $1.4M
HIGH_MIN = 2_500_000   # high tier: > $2.5M
# mid tier: $1.4M – $2.5M


# ---------------------------------------------------------------------------
# Dollar-value parser — requires NIL context near the dollar figure
# ---------------------------------------------------------------------------

_NIL_CONTEXT_RE = re.compile(
    r'\b(?:NIL|nil valuation|nil value|on3|opendorse|name image likeness|collective)\b',
    re.IGNORECASE,
)

# On3 specific: "NIL Valuation $X.XM" or "$X.X Million NIL"
_ON3_RE = re.compile(
    r'NIL\s+[Vv]aluation[:\s]+\$\s*([\d,.]+)\s*(?:million|M)\b'
    r'|\$\s*([\d,.]+)\s*(?:million|M)\b\s*NIL',
    re.IGNORECASE,
)

# Generic "$X million" with NIL context nearby
_MILLION_RE = re.compile(r'\$\s*([\d,.]+)\s*(?:million|M)\b', re.IGNORECASE)

# Range: "$X – $Y million"
_RANGE_RE = re.compile(
    r'\$\s*([\d,.]+)\s*(?:million|M)?\s*[-–]\s*\$?\s*([\d,.]+)\s*(?:million|M)\b',
    re.IGNORECASE,
)


def _float(raw: str) -> float:
    return float(raw.replace(',', ''))


def _in_range(dollars: float) -> bool:
    return 300_000 <= dollars <= NIL_MAX


def _has_nil_context(text: str, pos: int) -> bool:
    window = text[max(0, pos - 150): pos + 150]
    return bool(_NIL_CONTEXT_RE.search(window))


def parse_nil_value(text: str) -> float | None:
    """Extract individual NIL dollar amount from snippet. Returns dollars or None."""
    # On3-style structured result (highest confidence)
    m = _ON3_RE.search(text)
    if m:
        raw = m.group(1) or m.group(2)
        val = _float(raw) * 1_000_000
        if _in_range(val):
            return round(val)

    # Range → midpoint, but only with NIL context
    m = _RANGE_RE.search(text)
    if m and _has_nil_context(text, m.start()):
        lo = _float(m.group(1))
        hi = _float(m.group(2))
        if lo < 50:
            lo *= 1_000_000
        if hi < 50:
            hi *= 1_000_000
        mid = (lo + hi) / 2
        if _in_range(mid):
            return round(mid)

    # Generic "$X million" — require NIL context AND player name in window
    m = _MILLION_RE.search(text)
    if m and _has_nil_context(text, m.start()):
        val = _float(m.group(1)) * 1_000_000
        if _in_range(val):
            return round(val)

    return None


def search_nil_value(name: str, school: str) -> float | None:
    """Run targeted DDG queries and return the first valid NIL value."""
    first, *rest = name.split()
    last = rest[-1] if rest else ""

    queries = [
        f'"{name}" NIL valuation site:on3.com',
        f'"{name}" "{school}" NIL valuation',
        f'"{first} {last}" NIL value college football 2025',
    ]
    for query in queries:
        try:
            results = DDGS().text(query, max_results=6)
            for r in (results or []):
                snippet = f"{r.get('title', '')} {r.get('body', '')}"
                # Extra guard: player's last name must appear in the snippet
                if last.lower() not in snippet.lower():
                    continue
                val = parse_nil_value(snippet)
                if val is not None:
                    return val
        except Exception as e:
            tqdm.write(f"  DDG error ({name}): {e}")
        time.sleep(SEARCH_DELAY)
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_eligible_players(client, season: int | None = None) -> list[dict]:
    """Players who have BOTH a performance_stats row AND instagram_followers > 0."""
    stats_ids: set[int] = set()
    start = 0
    while True:
        q = client.table("players").select("id,name,school,position,performance_stats!inner(player_id)")
        if season:
            q = q.eq("season", season)
        batch = q.range(start, start + PAGE_SIZE - 1).execute().data or []
        for r in batch:
            stats_ids.add(r["id"])
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    social_ids: set[int] = set()
    start = 0
    while True:
        batch = (
            client.table("social_media")
            .select("player_id")
            .gt("instagram_followers", 0)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data or []
        )
        for r in batch:
            social_ids.add(r["player_id"])
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    eligible_ids = stats_ids & social_ids

    players = []
    start = 0
    while True:
        batch = (
            client.table("players")
            .select("id,name,school,position")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
            .data or []
        )
        for r in batch:
            if r["id"] in eligible_ids:
                players.append(r)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return players


def load_existing_names() -> set[str]:
    if not os.path.exists(WEB_PATH):
        return set()
    with open(WEB_PATH) as f:
        return {e["name"].lower() for e in json.load(f)}


def append_label(entry: dict):
    data = []
    if os.path.exists(WEB_PATH):
        with open(WEB_PATH) as f:
            data = json.load(f)
    data.append(entry)
    with open(WEB_PATH, 'w') as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Tier sampling
# ---------------------------------------------------------------------------

def tier_sample(players: list[dict], per_tier: int) -> list[dict]:
    """
    Load the calibrated predictions CSV, assign each eligible player a tier
    (low / mid / high) by predicted NIL value, then sample `per_tier` from each.
    Players not in the CSV fall into the 'mid' bucket.
    """
    if not os.path.exists(CSV_PATH):
        print(f"  WARNING: {CSV_PATH} not found — falling back to random sample")
        random.shuffle(players)
        return players[:per_tier * 3]

    df = pd.read_csv(CSV_PATH)[["name", "school", "nil_value"]]
    # build lookup: (lower name, lower school) → predicted nil
    pred = {
        (row["name"].lower(), row["school"].lower()): row["nil_value"]
        for _, row in df.iterrows()
    }

    low, mid, high = [], [], []
    for p in players:
        key = (p["name"].lower(), p["school"].lower())
        val = pred.get(key, 1_800_000)   # default to mid if not found
        if val < LOW_MAX:
            low.append(p)
        elif val >= HIGH_MIN:
            high.append(p)
        else:
            mid.append(p)

    print(f"  Tier counts — low: {len(low)}, mid: {len(mid)}, high: {len(high)}")

    random.seed(42)
    sampled = (
        random.sample(low,  min(per_tier, len(low)))  +
        random.sample(mid,  min(per_tier, len(mid)))  +
        random.sample(high, min(per_tier, len(high)))
    )
    random.shuffle(sampled)
    return sampled


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def ingest(
    max_players: int | None = None,
    season: int | None = None,
    per_tier: int | None = None,
):
    client = get_client()

    label = f"season={season}" if season else "all seasons"
    print(f"Fetching eligible players ({label}) with stats + followers...")
    players = fetch_eligible_players(client, season=season)
    print(f"  {len(players)} eligible players found")

    existing = load_existing_names()
    players = [p for p in players if p["name"].lower() not in existing]
    print(f"  {len(existing)} already labeled — {len(players)} remaining")

    if per_tier:
        print(f"\nTier-sampling {per_tier} players from each of low / mid / high...")
        players = tier_sample(players, per_tier)
        print(f"  Selected {len(players)} players across tiers")
    elif max_players:
        players = players[:max_players]
        print(f"  Capped at {max_players}")

    print()

    found = 0
    not_found = 0

    for p in tqdm(players, desc="NIL search", unit="player"):
        val = search_nil_value(p["name"], p["school"])

        if val is not None:
            entry = {
                "name": p["name"],
                "school": p["school"],
                "position": p.get("position") or "",
                "nil_value": val,
                "source": "web_search_2025",
            }
            append_label(entry)
            found += 1
            tqdm.write(f"  ✓ {p['name']} ({p['school']}): ${val:,.0f}")
        else:
            not_found += 1

    total = len(load_existing_names())
    print(f"\nDone.")
    print(f"  Found & saved : {found}")
    print(f"  No value found: {not_found}")
    print(f"  Total labels  : {total} (was 48)")
    print(f"\nNext: python src/valuation/calibrate_model.py --season 2024")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pull NIL valuations from DuckDuckGo for DB players with stats+followers"
    )
    parser.add_argument("--tier-sample", type=int, default=None, metavar="N",
                        help="Sample N players from each of low/mid/high tiers (recommended)")
    parser.add_argument("--max-players", type=int, default=None,
                        help="Cap total players (non-tiered mode)")
    parser.add_argument("--season", type=int, default=None,
                        help="Filter players by season (e.g. 2024)")
    args = parser.parse_args()
    ingest(
        max_players=args.max_players,
        season=args.season,
        per_tier=args.tier_sample,
    )
