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
    query = f"{name} {school} site:instagram.com"
    try:
        results = DDGS().text(query, max_results=5)
        for r in (results or []):
            username = extract_ig_username(r.get("href") or "")
            if username:
                return username
    except Exception as e:
        tqdm.write(f"  DDG error for {name}: {e}")
    return None


# ---------------------------------------------------------------------------
# Step 2: scrape instagram.com/{username}/ → follower count
# ---------------------------------------------------------------------------

def scrape_ig_profile(username: str) -> dict | None:
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    try:
        resp = requests.get(url, headers=IG_HEADERS, timeout=15)
        if resp.status_code == 200:
            user = resp.json().get("data", {}).get("user") or {}
            followers = user.get("edge_followed_by", {}).get("count")
            if followers is not None:
                return {
                    "instagram_followers": int(followers),
                    "verified_instagram": user.get("is_verified"),
                }
        elif resp.status_code == 404:
            return None  # profile doesn't exist
        else:
            tqdm.write(f"  IG API {resp.status_code} for {username}")
    except requests.exceptions.RequestException as e:
        tqdm.write(f"  Request error ({username}): {e}")
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_players(client, season: int = None) -> list[dict]:
    page_size = 1000
    start = 0
    rows = []
    while True:
        query = client.table("players").select("id,name,school")
        if season is not None:
            query = query.eq("season", season)
        batch = query.range(start, start + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def already_fetched(client) -> set[int]:
    page_size = 1000
    start = 0
    ids = set()
    while True:
        batch = (
            client.table("social_media")
            .select("player_id")
            .range(start, start + page_size - 1)
            .execute()
            .data or []
        )
        for row in batch:
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

def ingest(skip_existing: bool = True, max_players: int = None, season: int = None):
    client = get_client()
    players = fetch_players(client, season=season)
    label = f"season={season}" if season else "all seasons"
    print(f"Found {len(players)} players in DB ({label})")

    if skip_existing:
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
        time.sleep(SEARCH_DELAY)

        # Step 2: scrape follower count
        profile = None
        if username:
            profile = scrape_ig_profile(username)
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
    parser.add_argument("--refetch", action="store_true", help="Re-fetch already saved players")
    parser.add_argument("--max-players", type=int, default=None, help="Limit for testing")
    parser.add_argument("--season", type=int, default=None, help="Filter players by season (e.g. 2024)")
    args = parser.parse_args()
    ingest(skip_existing=not args.refetch, max_players=args.max_players, season=args.season)
