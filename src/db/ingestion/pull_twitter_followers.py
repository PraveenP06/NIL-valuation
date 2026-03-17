import os
import sys
import re
import time
import requests
import argparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from dotenv import load_dotenv
from tqdm import tqdm
# TWITTER FOLLOWER FETCHER — Playwright-based, no API key needed
#
# Flow per player:
#   1. Google search "{name} {school} twitter" → find twitter.com/username
#   2. Playwright visits twitter.com/username → scrapes follower count
#   3. Upsert into existing social_media row (preserves Instagram data)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client
from db.crud import upsert_social_media
from db.models import SocialMediaCreate

load_dotenv()

APIFY_TOKEN  = os.getenv("APIFY_API_KEY")
APIFY_BASE   = "https://api.apify.com/v2"
GOOGLE_ACTOR = "apify~google-search-scraper"
SAVE_INTERVAL = 50
BATCH_SIZE    = 20


# ---------------------------------------------------------------------------
# Google search via Apify → Twitter username
# ---------------------------------------------------------------------------

def run_google(queries: list[str]) -> list[dict] | None:
    url = f"{APIFY_BASE}/acts/{GOOGLE_ACTOR}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN, "timeout": 120}
    try:
        resp = requests.post(
            url,
            json={"queries": "\n".join(queries), "maxPagesPerQuery": 1, "resultsPerPage": 5},
            params=params,
            timeout=150,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data if isinstance(data, list) else []
        tqdm.write(f"  Google error {resp.status_code}: {resp.text[:100]}")
        return None
    except Exception as e:
        tqdm.write(f"  Google request failed: {e}")
        return None


def extract_twitter_username(url: str) -> str | None:
    match = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)(?:/|$|\?)", url)
    if match:
        username = match.group(1).lower()
        if username not in {"home", "search", "explore", "notifications", "messages", "i", "intent"}:
            return username
    return None


def google_find_twitter_usernames(players: list[dict]) -> dict[int, str]:
    """Returns {player_id: twitter_username}"""
    pid_to_username: dict[int, str] = {}
    queries = [f"{p['name']} {p['school']} twitter" for p in players]
    pid_by_query = {f"{p['name']} {p['school']} twitter": p["id"] for p in players}

    batches = [queries[i:i+BATCH_SIZE] for i in range(0, len(queries), BATCH_SIZE)]
    for batch in tqdm(batches, desc="  Google→Twitter", unit="batch", leave=False):
        results = run_google(batch)
        if results is None:
            continue
        results_by_query: dict[str, list] = {}
        for r in results:
            q = (r.get("searchQuery") or {}).get("term") or r.get("query") or ""
            results_by_query.setdefault(q, []).append(r)

        for q, pid in pid_by_query.items():
            if pid in pid_to_username:
                continue
            for hit in results_by_query.get(q, []):
                for result in (hit.get("organicResults") or []):
                    username = extract_twitter_username(result.get("url") or "")
                    if username:
                        pid_to_username[pid] = username
                        break
                if pid in pid_to_username:
                    break

    return pid_to_username


# ---------------------------------------------------------------------------
# Playwright → scrape follower count from Twitter profile
# ---------------------------------------------------------------------------

def parse_follower_count(text: str) -> int | None:
    """Convert '12.3K', '1.2M', '845' → integer."""
    text = text.strip().replace(",", "")
    match = re.match(r"([\d.]+)([KkMm]?)", text)
    if not match:
        return None
    num = float(match.group(1))
    suffix = match.group(2).upper()
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    return int(num)


def scrape_twitter_followers(username: str, page) -> int | None:
    """Visit a Twitter/X profile page and extract follower count."""
    try:
        page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)  # let JS render

        # Follower count appears in an <a> with href="/{username}/verified_followers"
        # or "/{username}/followers" — look for the text near "Followers"
        followers_link = page.query_selector(f'a[href="/{username}/verified_followers"], a[href="/{username}/followers"]')
        if followers_link:
            text = followers_link.inner_text()
            # text is like "12.3K\nFollowers"
            num_text = text.split()[0]
            return parse_follower_count(num_text)

        # Fallback: search all spans for a number near the word "Followers"
        spans = page.query_selector_all("span")
        for i, span in enumerate(spans):
            t = span.inner_text().strip()
            if t.lower() == "followers" and i > 0:
                count_text = spans[i - 1].inner_text().strip()
                result = parse_follower_count(count_text)
                if result:
                    return result

        return None
    except PlaywrightTimeout:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_players_missing_twitter(client, refetch: bool = False) -> list[dict]:
    """Get players who have a social_media row but no twitter_followers yet."""
    page_size = 1000
    start = 0
    sm_rows = []
    while True:
        query = client.table("social_media").select("player_id")
        if not refetch:
            query = query.is_("twitter_followers", "null")
        batch = (
            query
            .range(start, start + page_size - 1)
            .execute()
            .data or []
        )
        sm_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    if not sm_rows:
        return []

    # Bulk fetch player details in one query per batch
    player_ids = [r["player_id"] for r in sm_rows]
    players_map = {}
    for i in range(0, len(player_ids), 500):
        chunk_ids = player_ids[i:i+500]
        rows = client.table("players").select("id,name,school").in_("id", chunk_ids).execute().data or []
        for p in rows:
            players_map[p["id"]] = p

    return [players_map[pid] for pid in player_ids if pid in players_map]


def save_twitter_data(client, pid: int, twitter_followers: int | None, username: str | None):
    existing = client.table("social_media").select("*").eq("player_id", pid).limit(1).execute().data
    if not existing:
        return
    row = existing[0]
    ig = row.get("instagram_followers")
    total = sum(v for v in [ig, twitter_followers] if v) or None

    social = SocialMediaCreate(
        player_id=pid,
        player_name=row.get("player_name"),
        instagram_followers=ig,
        twitter_followers=twitter_followers,
        total_followers=total,
        engagement_rate=row.get("engagement_rate"),
        avg_post_likes=row.get("avg_post_likes"),
        verified_instagram=row.get("verified_instagram"),
        verified_twitter=None,
    )
    upsert_social_media(social)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def ingest(max_players: int = None, refetch: bool = False):
    client = get_client()
    players = fetch_players_missing_twitter(client, refetch=refetch)
    print(f"Players missing Twitter data: {len(players)}")

    if max_players:
        players = players[:max_players]
        print(f"Capped at {max_players} for this run")

    print()
    chunks = [players[i:i+SAVE_INTERVAL] for i in range(0, len(players), SAVE_INTERVAL)]
    total_found = 0
    total_not_found = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        for chunk_num, chunk in enumerate(chunks, 1):
            print(f"--- Chunk {chunk_num}/{len(chunks)} ({len(chunk)} players) ---")

            # Step 1: Google → usernames
            pid_to_username = google_find_twitter_usernames(chunk)
            print(f"  Found usernames: {len(pid_to_username)} / {len(chunk)}")

            if not pid_to_username:
                print("  No usernames found — credits may be exhausted. Stopping.")
                break

            # Step 2: Playwright → follower counts
            chunk_found = 0
            login_wall_hit = False
            for player in tqdm(chunk, desc="  Scraping Twitter", unit="player", leave=False):
                pid = player["id"]
                username = pid_to_username.get(pid)

                followers = None
                if username:
                    # Check for login wall before scraping
                    page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    if page.query_selector('[data-testid="LoginForm"], [href="/login"]'):
                        tqdm.write("  WARNING: Login wall detected — stopping scrape loop early.")
                        login_wall_hit = True
                        total_not_found += 1
                        break
                    followers = scrape_twitter_followers(username, page)
                    time.sleep(1.5)  # polite delay

                try:
                    save_twitter_data(client, pid, followers, username)
                    if followers:
                        chunk_found += 1
                    else:
                        total_not_found += 1
                except Exception as e:
                    tqdm.write(f"  DB error for {player['name']}: {e}")
                    total_not_found += 1

            if login_wall_hit:
                break

            total_found += chunk_found
            print(f"  With followers: {chunk_found} | Total so far: {total_found}\n")

        browser.close()

    print(f"✅ Done!")
    print(f"  ✓ Found followers:  {total_found}")
    print(f"  ✗ Not found:        {total_not_found}")
    print(f"\n  Re-run anytime — skips players already having Twitter data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Twitter follower counts via Playwright")
    parser.add_argument("--max-players", type=int, default=None, help="Limit for testing")
    parser.add_argument("--refetch", action="store_true", help="Re-process players already attempted (ignore null filter)")
    args = parser.parse_args()
    ingest(max_players=args.max_players, refetch=args.refetch)
