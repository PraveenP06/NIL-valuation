import os
import sys
import re
import time
import requests
import argparse
from dotenv import load_dotenv
from tqdm import tqdm
# SOCIAL MEDIA FETCHER — two-step approach:
#   Step 1: Google search "{name} {school} instagram" → find real Instagram username
#   Step 2: Look up that username via Instagram scraper → get follower count
#
# This is far more reliable than guessing usernames because Google already
# knows which account belongs to the athlete.

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client
from db.crud import upsert_social_media
from db.models import SocialMediaCreate

load_dotenv()

APIFY_TOKEN   = os.getenv("APIFY_API_KEY")
APIFY_BASE    = "https://api.apify.com/v2"
GOOGLE_ACTOR  = "apify~google-search-scraper"
IG_ACTOR      = "apify~instagram-profile-scraper"

BATCH_SIZE    = 20   # Google queries per Apify call


# ---------------------------------------------------------------------------
# Apify helper
# ---------------------------------------------------------------------------

def run_actor(actor_id: str, input_data: dict, timeout: int = 120) -> list[dict] | None:
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN, "timeout": timeout}
    try:
        resp = requests.post(url, json=input_data, params=params, timeout=timeout + 30)
        if resp.status_code in (200, 201):
            data = resp.json()
            return data if isinstance(data, list) else []
        tqdm.write(f"  Apify {actor_id} error {resp.status_code}: {resp.text[:150]}")
        return None
    except requests.exceptions.Timeout:
        tqdm.write(f"  Apify {actor_id} timed out")
        return None
    except requests.exceptions.ConnectionError:
        tqdm.write(f"  Apify {actor_id} connection error")
        return None


# ---------------------------------------------------------------------------
# Step 1: Google search → Instagram username
# ---------------------------------------------------------------------------

def extract_ig_username(url: str) -> str | None:
    """Pull the username out of an instagram.com URL."""
    match = re.search(r"instagram\.com/([A-Za-z0-9._]+)/?", url)
    if match:
        username = match.group(1)
        # Filter out Instagram's own pages
        if username.lower() not in {"p", "reel", "stories", "explore", "accounts", "instagram"}:
            return username
    return None


def google_search_batch(queries: list[str]) -> list[dict] | None:
    """Run multiple Google searches in one Apify call."""
    return run_actor(
        GOOGLE_ACTOR,
        {
            "queries": "\n".join(queries),
            "maxPagesPerQuery": 1,
            "resultsPerPage": 5,
        },
        timeout=120,
    )


def find_ig_usernames(players: list[dict]) -> dict[int, str]:
    """
    For each player, Google search their name + school + instagram.
    Returns {player_id: instagram_username}.
    """
    pid_to_username: dict[int, str] = {}
    pid_by_query: dict[str, int] = {}

    queries = []
    for p in players:
        q = f"{p['name']} {p['school']} instagram"
        queries.append(q)
        pid_by_query[q] = p["id"]

    batches = [queries[i:i+BATCH_SIZE] for i in range(0, len(queries), BATCH_SIZE)]

    for batch in tqdm(batches, desc="Google searching", unit="batch"):
        results = google_search_batch(batch)
        if results is None:
            continue

        # Group results by their query
        results_by_query: dict[str, list] = {}
        for r in results:
            q = r.get("searchQuery", {}).get("term") or r.get("query") or ""
            results_by_query.setdefault(q, []).append(r)

        for q, pid in pid_by_query.items():
            if pid in pid_to_username:
                continue
            hits = results_by_query.get(q, [])
            for hit in hits:
                # Check organic results for instagram.com URLs
                organic = hit.get("organicResults") or []
                for result in organic:
                    url = result.get("url") or ""
                    username = extract_ig_username(url)
                    if username:
                        pid_to_username[pid] = username
                        break
                if pid in pid_to_username:
                    break

    return pid_to_username


# ---------------------------------------------------------------------------
# Step 2: Instagram profile lookup → follower count
# ---------------------------------------------------------------------------

def lookup_ig_profiles(usernames: list[str]) -> dict[str, dict]:
    """
    Look up Instagram profiles by username.
    Returns {username: {followers, verified}}.
    """
    username_to_data: dict[str, dict] = {}
    batches = [usernames[i:i+50] for i in range(0, len(usernames), 50)]

    for batch in tqdm(batches, desc="Instagram lookups", unit="batch"):
        results = run_actor(IG_ACTOR, {"usernames": batch}, timeout=120)
        if results is None:
            continue
        for r in results:
            uname = (r.get("username") or "").lower()
            if uname:
                username_to_data[uname] = {
                    "instagram_followers": r.get("followersCount") or r.get("followers_count"),
                    "verified_instagram": r.get("isVerified") or r.get("verified"),
                }

    return username_to_data


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_players(client) -> list[dict]:
    page_size = 1000
    start = 0
    rows = []
    while True:
        batch = client.table("players").select("id,name,school").range(start, start + page_size - 1).execute().data or []
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
        batch = client.table("social_media").select("player_id").range(start, start + page_size - 1).execute().data or []
        for row in batch:
            ids.add(row["player_id"])
        if len(batch) < page_size:
            break
        start += page_size
    return ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SAVE_INTERVAL = 100  # save to DB every N players so progress isn't lost if credits run out


def save_chunk(client, players: list[dict], pid_to_username: dict, username_to_data: dict) -> tuple[int, int]:
    """Save a chunk of players to DB. Returns (saved, not_found).
    Every player gets a record — unmatched ones have null followers but name is always set."""
    saved = 0
    not_found = 0
    for p in players:
        pid = p["id"]
        username = pid_to_username.get(pid)
        profile = username_to_data.get(username.lower()) if username else None

        ig = profile.get("instagram_followers") if profile else None
        social = SocialMediaCreate(
            player_id=pid,
            player_name=p["name"],
            instagram_followers=ig,
            twitter_followers=None,
            total_followers=ig,
            engagement_rate=None,
            avg_post_likes=None,
            verified_instagram=profile.get("verified_instagram") if profile else None,
            verified_twitter=None,
        )
        try:
            upsert_social_media(social)
            if ig:
                saved += 1
            else:
                not_found += 1
        except Exception as e:
            tqdm.write(f"  DB error for {p['name']}: {e}")
    return saved, not_found


def ingest(skip_existing: bool = True, max_players: int = None):
    if not APIFY_TOKEN:
        print("ERROR: APIFY_API_KEY not found in .env")
        return

    client = get_client()
    players = fetch_players(client)
    print(f"Found {len(players)} players in DB")

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
    chunks = [players[i:i+SAVE_INTERVAL] for i in range(0, len(players), SAVE_INTERVAL)]
    print(f"Processing {len(players)} players in {len(chunks)} chunks of {SAVE_INTERVAL}\n")

    for chunk_num, chunk in enumerate(chunks, 1):
        print(f"--- Chunk {chunk_num}/{len(chunks)} ({len(chunk)} players) ---")

        # Step 1: Google search → usernames
        pid_to_username = find_ig_usernames(chunk)
        print(f"  Found usernames: {len(pid_to_username)} / {len(chunk)}")

        if not pid_to_username:
            print("  No usernames found — credits may be exhausted. Stopping.")
            break

        # Step 2: Instagram lookup → follower counts
        all_usernames = list(set(pid_to_username.values()))
        username_to_data = lookup_ig_profiles(all_usernames)
        print(f"  Got IG profiles: {len(username_to_data)} / {len(all_usernames)}")

        if not username_to_data:
            print("  No profiles returned — skipping chunk (timeout or temporary error).")
            continue

        # Step 3: Save this chunk immediately
        saved, not_found = save_chunk(client, chunk, pid_to_username, username_to_data)
        total_saved += saved
        total_not_found += not_found
        print(f"  Saved: {saved} | Not found: {not_found} | Total saved so far: {total_saved}\n")

    print(f"✅ Done!")
    print(f"  ✓ Total saved:     {total_saved}")
    print(f"  ✗ Total not found: {total_not_found}")
    print(f"\n  Re-run anytime — already saved players will be skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch social media data via Google + Apify")
    parser.add_argument("--refetch", action="store_true", help="Re-fetch already saved players")
    parser.add_argument("--max-players", type=int, default=None, help="Limit for testing")
    args = parser.parse_args()
    ingest(skip_existing=not args.refetch, max_players=args.max_players)
