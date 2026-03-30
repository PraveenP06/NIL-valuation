"""
Pull recruit star ratings from CFBD and update players table.

Strategy:
  - Pull recruiting classes for years 2021-2025 (covers all current players)
  - Match recruits to players by normalized (name, committedTo school)
  - Update players.recruiting_stars and players.recruiting_rating

Usage:
    python src/db/ingestion/pull_recruit_rankings.py
"""
import os
import sys
import re
import requests
from dotenv import load_dotenv
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client

load_dotenv()

API_KEY  = os.getenv("CFB_API_KEY")
if not API_KEY:
    raise RuntimeError("CFB_API_KEY is not set. Add it to your .env file.")
BASE_URL = "https://api.collegefootballdata.com"
HEADERS  = {"Authorization": f"Bearer {API_KEY}"}

# Cover FR/SO/JR/SR for both 2024 and 2025 rosters
RECRUIT_YEARS = [2021, 2022, 2023, 2024, 2025]


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())


def fetch_recruits(year: int) -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/recruiting/players",
        headers=HEADERS,
        params={"year": year, "classification": "HighSchool"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json() or []


def main():
    client = get_client()

    # Load all players from DB
    print("Loading players from DB...")
    page_size, start, rows = 1000, 0, []
    while True:
        batch = (
            client.table("players")
            .select("id,name,school,season,class_year,recruiting_stars,recruiting_rating")
            .range(start, start + page_size - 1)
            .execute()
            .data or []
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    print(f"  {len(rows)} players loaded")

    # Build lookup: (norm_name, norm_school) -> player_id
    lookup: dict[tuple, int] = {}
    name_only: dict[str, list[int]] = {}
    for p in rows:
        key = (norm(p["name"]), norm(p["school"] or ""))
        lookup[key] = p["id"]
        name_only.setdefault(norm(p["name"]), []).append(p["id"])

    # Pull all recruit classes
    all_recruits: list[dict] = []
    for year in RECRUIT_YEARS:
        print(f"Fetching {year} recruiting class...", end=" ")
        try:
            recruits = fetch_recruits(year)
            print(f"{len(recruits)} recruits")
            all_recruits.extend(recruits)
        except Exception as e:
            print(f"ERROR: {e}")

    # Match recruits → players and collect updates
    updates: dict[int, dict] = {}  # player_id -> {stars, rating}

    for r in all_recruits:
        name       = norm(r.get("name") or "")
        committed  = norm(r.get("committedTo") or "")
        stars      = r.get("stars")
        rating     = r.get("rating")

        if not name or (not stars and not rating):
            continue

        pid = lookup.get((name, committed))
        if not pid and committed:
            # Try name-only if unique
            cands = name_only.get(name, [])
            pid = cands[0] if len(cands) == 1 else None
        if not pid:
            continue

        # Keep the best (highest stars) if player appears in multiple classes
        existing = updates.get(pid, {})
        if (stars or 0) >= (existing.get("recruiting_stars") or 0):
            updates[pid] = {
                "recruiting_stars":  stars,
                "recruiting_rating": rating,
            }

    print(f"\nMatched {len(updates)} players to recruit data")

    update_list = [(pid, data["recruiting_stars"], data["recruiting_rating"])
                   for pid, data in updates.items()]
    updated = 0
    for pid, stars, rating in tqdm(update_list, desc="Updating players"):
        try:
            client.table("players").update({
                "recruiting_stars":  stars,
                "recruiting_rating": rating,
            }).eq("id", pid).execute()
            updated += 1
        except Exception as e:
            tqdm.write(f"  Error updating player {pid}: {e}")

    print(f"\n✅ Done! Updated {updated} players with recruit ratings")

    # Summary
    stars_dist: dict[int, int] = {}
    for _, stars, _ in update_list:
        s = stars or 0
        stars_dist[s] = stars_dist.get(s, 0) + 1
    print("\nStars distribution:")
    for s in sorted(stars_dist, reverse=True):
        print(f"  {s}★: {stars_dist[s]}")


if __name__ == "__main__":
    main()
