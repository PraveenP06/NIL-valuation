import os
import sys
import re
import time
import argparse
from datetime import datetime, timezone
import requests
from ddgs import DDGS
from tqdm import tqdm

# SOCIAL MEDIA FETCHER — free two-step approach:
#   Step 1: DuckDuckGo search "{name} {school} instagram" → find Instagram username
#   Step 2: requests scrape of instagram.com/{username}/ → parse follower count from page JSON

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client
from dotenv import load_dotenv

load_dotenv()

SEARCH_DELAY  = 1.5   # seconds between DuckDuckGo queries
INSTA_DELAY   = 2.0   # seconds between Instagram requests
SAVE_INTERVAL = 50    # save to DB every N players

IG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-ig-app-id": "936619743392459",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
}


# ---------------------------------------------------------------------------
# Step 1: DuckDuckGo search → Instagram username
# ---------------------------------------------------------------------------

_IG_SKIP = {"p", "reel", "stories", "explore", "accounts", "instagram", "popular"}


def extract_ig_username(url: str) -> str | None:
    match = re.search(r"instagram\.com/([A-Za-z0-9._]+)/?", url)
    if match:
        username = match.group(1)
        if username.lower() not in _IG_SKIP:
            return username
    return None


def ddg_find_username(name: str, school: str) -> str | None:
    # Include "football" to avoid matching celebrity accounts with the same name
    queries = [
        f"{name} {school} football site:instagram.com",
        f"{name} {school} site:instagram.com",
    ]
    for query in queries:
        try:
            results = DDGS().text(query, max_results=5)
            for r in (results or []):
                username = extract_ig_username(r.get("href") or "")
                if username:
                    return username
        except Exception as e:
            tqdm.write(f"  DDG error for {name}: {e}")
        time.sleep(SEARCH_DELAY)
    return None


# ---------------------------------------------------------------------------
# Step 2: scrape instagram.com/{username}/ → follower count
# ---------------------------------------------------------------------------

def scrape_ig_profile(username: str, player_last_name: str = "") -> dict | None:
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    try:
        resp = requests.get(url, headers=IG_HEADERS, timeout=15)
        if resp.status_code == 200:
            user = resp.json().get("data", {}).get("user") or {}
            followers = user.get("edge_followed_by", {}).get("count")
            if followers is not None:
                # Validate: the account's display name must contain the player's last name.
                # This prevents matching celebrity accounts with common player names
                # (e.g., "Willie Nelson", "AJ Green" the NFL player).
                if player_last_name:
                    full_name = (user.get("full_name") or "").lower()
                    username_lower = username.lower()
                    last = player_last_name.lower()
                    if last not in full_name and last not in username_lower:
                        tqdm.write(f"  ✗ Name mismatch: @{username} ({user.get('full_name')!r}) ≠ {player_last_name!r}")
                        return None
                return {
                    "instagram_followers": int(followers),
                    "verified_instagram": user.get("is_verified"),
                }
        elif resp.status_code == 404:
            return None
        else:
            tqdm.write(f"  IG API {resp.status_code} for {username}")
    except requests.exceptions.RequestException as e:
        tqdm.write(f"  Request error ({username}): {e}")
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_players(client, season: int = None, stats_only: bool = False) -> list[dict]:
    page_size = 1000
    start = 0
    rows = []
    while True:
        if stats_only:
            # Only return players who have a performance_stats row
            query = client.table("players").select("id,name,school,performance_stats!inner(player_id)")
        else:
            query = client.table("players").select("id,name,school")
        if season is not None:
            query = query.eq("season", season)
        batch = query.range(start, start + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return [{"id": r["id"], "name": r["name"], "school": r["school"]} for r in rows]


def already_fetched(client) -> set[int]:
    """Return player_ids that already have a non-null follower count."""
    page_size = 1000
    start = 0
    ids = set()
    while True:
        batch = (
            client.table("social_media")
            .select("player_id,total_followers")
            .range(start, start + page_size - 1)
            .execute()
            .data or []
        )
        for row in batch:
            # Only skip if we have a real (non-null) follower count
            if row.get("total_followers") is not None:
                ids.add(row["player_id"])
        if len(batch) < page_size:
            break
        start += page_size
    return ids


def save_player(client, p: dict, profile: dict | None) -> bool:
    ig = profile.get("instagram_followers") if profile else None
    data = {
        "player_id": p["id"],
        "player_name": p["name"],
        "instagram_followers": ig,
        "twitter_followers": None,
        "total_followers": ig,
        "engagement_rate": None,
        "avg_post_likes": None,
        "verified_instagram": profile.get("verified_instagram") if profile else None,
        "verified_twitter": None,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    client.table("social_media").upsert(data, on_conflict="player_id").execute()
    return ig is not None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_nulled_players(client, season: int = None) -> list[dict]:
    """Return players who have a social_media row with null total_followers (bad prior scrape)."""
    page_size = 1000
    start = 0
    null_ids: set[int] = set()
    while True:
        batch = (
            client.table("social_media")
            .select("player_id")
            .is_("total_followers", "null")
            .range(start, start + page_size - 1)
            .execute()
            .data or []
        )
        for r in batch:
            null_ids.add(r["player_id"])
        if len(batch) < page_size:
            break
        start += page_size

    all_players = fetch_players(client, season=season)
    return [p for p in all_players if p["id"] in null_ids]


def ingest(skip_existing: bool = True, max_players: int = None, season: int = None,
           stats_only: bool = False, refetch_nulled: bool = False):
    client = get_client()

    if refetch_nulled:
        players = fetch_nulled_players(client, season=season)
        print(f"Re-scraping {len(players)} players with null follower counts")
    else:
        players = fetch_players(client, season=season, stats_only=stats_only)
        label = f"season={season}" if season else "all seasons"
        print(f"Found {len(players)} players in DB ({label})")

    if skip_existing and not refetch_nulled:
        done = already_fetched(client)
        players = [p for p in players if p["id"] not in done]
        print(f"Skipping {len(done)} already fetched → {len(players)} remaining")

    if max_players:
        players = players[:max_players]
        print(f"Capped at {max_players} for this run")

    print()

    total_saved = 0
    total_not_found = 0
    chunk_buffer: list[tuple[dict, dict | None]] = []

    for i, p in enumerate(tqdm(players, desc="Players", unit="player")):
        # Step 1: find username via DuckDuckGo
        username = ddg_find_username(p["name"], p["school"])

        # Step 2: scrape follower count — pass last name for validation
        profile = None
        if username:
            parts = p["name"].split()
            last_name = parts[-1] if len(parts) > 1 else parts[0]
            profile = scrape_ig_profile(username, player_last_name=last_name)
            time.sleep(INSTA_DELAY)

        chunk_buffer.append((p, profile))

        # Flush to DB every SAVE_INTERVAL
        if len(chunk_buffer) >= SAVE_INTERVAL:
            for player, prof in chunk_buffer:
                try:
                    found = save_player(client, player, prof)
                    if found:
                        total_saved += 1
                    else:
                        total_not_found += 1
                except Exception as e:
                    tqdm.write(f"  DB error for {player['name']}: {e}")
            tqdm.write(f"  Saved chunk — IG data found: {total_saved} / {i + 1}")
            chunk_buffer = []

    # Save remaining
    for player, prof in chunk_buffer:
        try:
            found = save_player(client, player, prof)
            if found:
                total_saved += 1
            else:
                total_not_found += 1
        except Exception as e:
            tqdm.write(f"  DB error for {player['name']}: {e}")

    print(f"\n✅ Done!")
    print(f"  ✓ Total saved:     {total_saved}")
    print(f"  ✗ Total not found: {total_not_found}")
    print(f"\n  Re-run anytime — already saved players will be skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch social media data via DuckDuckGo + requests scrape (free)")
    parser.add_argument("--refetch", action="store_true", help="Re-fetch all players (ignore existing)")
    parser.add_argument("--refetch-nulled", action="store_true", help="Only re-fetch players with null follower counts (bad previous scrapes)")
    parser.add_argument("--max-players", type=int, default=None, help="Limit for testing")
    parser.add_argument("--season", type=int, default=None, help="Filter players by season (e.g. 2024)")
    parser.add_argument("--stats-only", action="store_true", help="Only process players who have performance stats")
    args = parser.parse_args()
    ingest(
        skip_existing=not args.refetch,
        max_players=args.max_players,
        season=args.season,
        stats_only=args.stats_only,
        refetch_nulled=args.refetch_nulled,
    )
