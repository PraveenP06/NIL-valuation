"""
Scrape On3 NIL rankings for college football players.

Strategy:
  1. Intercept XHR/fetch network responses from On3 to find the rankings JSON API
  2. Fall back to extracting __NEXT_DATA__ embedded JSON
  3. Last resort: structured DOM scraping with correct field offsets

Output: data/on3_rankings.json

Usage:
    python src/db/ingestion/pull_on3_nil.py
    python src/db/ingestion/pull_on3_nil.py --pages 5
"""
import os
import sys
import re
import json
import time
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../../../data/on3_rankings.json")
BASE_URL    = "https://www.on3.com/nil/rankings/player/college/football/"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_money(text: str) -> float | None:
    if not text or str(text).strip() in ("—", "-", ""):
        return None
    text = str(text).strip().replace("$", "").replace(",", "")
    match = re.match(r"([\d.]+)([KkMm]?)", text)
    if not match:
        return None
    num = float(match.group(1))
    suffix = match.group(2).upper()
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    return num if num > 100 else None


def parse_followers(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    text = str(val).strip().replace(",", "")
    if text in ("—", "-", ""):
        return None
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


def normalize_class(text) -> int | None:
    if not text:
        return None
    t = str(text).upper().strip()
    if "FR" in t or t == "1":
        return 1
    if "SO" in t or t == "2":
        return 2
    if "JR" in t or t == "3":
        return 3
    if "SR" in t or t == "4":
        return 4
    return None


# ---------------------------------------------------------------------------
# Strategy 1: Network interception — catch the JSON API call On3 makes
# ---------------------------------------------------------------------------

def scrape_via_network(page, url: str) -> list[dict] | None:
    """Intercept On3's internal API calls and extract player JSON."""
    captured = []

    def handle_response(response):
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            resp_url = response.url.lower()
            # On3 API patterns
            if any(kw in resp_url for kw in ("nil", "ranking", "player", "athlete")):
                try:
                    body = response.json()
                    captured.append({"url": response.url, "body": body})
                except Exception:
                    pass
        except Exception:
            pass

    page.on("response", handle_response)

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except PlaywrightTimeout:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)
        except PlaywrightTimeout:
            pass

    page.remove_listener("response", handle_response)

    if not captured:
        return None

    # Find the response that looks most like a player list
    for item in captured:
        raw_players = _extract_players_from_api_body(item["body"])
        if raw_players and len(raw_players) > 3:
            print(f"    Got {len(raw_players)} players from API: {item['url']}")
            # Normalize via _parse_api_player so all downstream code sees consistent keys
            return [_parse_api_player(p, i + 1) for i, p in enumerate(raw_players)]

    return None


def _extract_players_from_api_body(body) -> list[dict] | None:
    """Walk the API response body to find player records."""
    if isinstance(body, list) and len(body) > 3:
        sample = body[0]
        if isinstance(sample, dict):
            keys = set(sample.keys())
            if keys & {"nilValue", "nil_value", "instagramFollowers", "player", "firstName", "name", "athlete"}:
                return body
    if isinstance(body, dict):
        for v in body.values():
            result = _extract_players_from_api_body(v)
            if result:
                return result
    return None


def _parse_api_player(raw: dict, rank: int) -> dict:
    """Normalize a player record from On3's API JSON."""
    # On3 nests the player object — try common patterns
    p   = raw.get("player") or raw.get("athlete") or raw
    ath = raw.get("athlete") or raw.get("player") or {}

    # Name
    name = (
        p.get("name")
        or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
        or ath.get("name", "")
        or raw.get("name", "")
    )

    # School (college team)
    team = p.get("team") or raw.get("team") or ath.get("currentTeam") or {}
    school = team.get("name") if isinstance(team, dict) else (team or None)
    if not school:
        school = p.get("school") or p.get("teamName") or raw.get("school")

    # Class year
    yr_raw = (
        p.get("year") or p.get("classYear") or p.get("eligibilityYear")
        or ath.get("year") or raw.get("year")
    )

    # Social
    ig  = parse_followers(raw.get("instagramFollowers") or p.get("instagramFollowers") or ath.get("instagramFollowers"))
    tik = parse_followers(raw.get("tiktokFollowers")    or p.get("tiktokFollowers")    or ath.get("tiktokFollowers"))
    tw  = parse_followers(raw.get("twitterFollowers")   or p.get("twitterFollowers")   or ath.get("twitterFollowers"))

    # NIL value
    nil = parse_money(raw.get("nilValue") or raw.get("nil_value") or raw.get("value"))

    return {
        "rank":               rank,
        "name":               name,
        "position":           p.get("position") or raw.get("position"),
        "school":             school,
        "class_year":         normalize_class(yr_raw),
        "nil_value":          nil,
        "instagram_followers": ig,
        "tiktok_followers":   tik,
        "twitter_followers":  tw,
        "source":             "on3_api",
    }


# ---------------------------------------------------------------------------
# Strategy 2: __NEXT_DATA__ embedded JSON
# ---------------------------------------------------------------------------

def scrape_via_nextdata(page) -> list[dict] | None:
    try:
        raw = page.evaluate("() => document.getElementById('__NEXT_DATA__')?.textContent")
        if not raw:
            return None
        data = json.loads(raw)
        players = _find_player_array_nextjs(data)
        if not players:
            return None
        print(f"    Found {len(players)} players in __NEXT_DATA__")
        result = []
        for i, p in enumerate(players):
            result.append(_parse_api_player(p, i + 1))
        return result
    except Exception:
        return None


def _find_player_array_nextjs(obj, depth=0) -> list | None:
    if depth > 12:
        return None
    if isinstance(obj, list) and len(obj) > 5:
        sample = obj[0] if obj else {}
        if isinstance(sample, dict):
            keys = set(sample.keys())
            if keys & {"nilValue", "nil_value", "instagramFollowers", "player", "firstName", "athlete"}:
                return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = _find_player_array_nextjs(v, depth + 1)
            if r:
                return r
    if isinstance(obj, list):
        for item in obj:
            r = _find_player_array_nextjs(item, depth + 1)
            if r:
                return r
    return None


# ---------------------------------------------------------------------------
# Strategy 3: DOM scraping with correct field positions
# ---------------------------------------------------------------------------

# On3's rankings page structure per player row (from manual inspection):
# The inner text of each row typically looks like:
#   {rank}
#   {player_name}
#   {position} | {class} | {height} | {weight}
#   {college_name}
#   {high_school_name}         ← this was tripping up the old parser
#   {city, state}
#   {nil_value}
#   {ig_followers}
#   {tik_followers}
#   {tw_followers}

def scrape_via_dom(page, page_num: int) -> list[dict]:
    """Structured DOM scraping using On3's row layout."""
    try:
        page.wait_for_selector('main', timeout=10000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(3000)

    # Find all player link elements — On3 links each player to /db/players/{slug}/
    player_links = page.query_selector_all('a[href*="/db/players/"]')

    if player_links:
        return _parse_from_player_links(page, player_links, page_num)

    # Fallback to row-based parsing
    return _parse_rows_structured(page, page_num)


def _parse_from_player_links(page, links, page_num: int) -> list[dict]:
    """Each player link contains or is near all their ranking data."""
    players = []
    start_rank = (page_num - 1) * 25 + 1
    seen_names = set()

    for i, link in enumerate(links):
        try:
            # The player name is the link text
            name = link.inner_text().strip()
            if not name or len(name) < 3 or name in seen_names:
                continue
            # Skip if it looks like a school or location
            if any(c.isdigit() for c in name) or name.startswith("("):
                continue
            seen_names.add(name)

            # Walk up to the row container to get context
            row = link
            for _ in range(6):
                parent = row.evaluate_handle("el => el.parentElement")
                if parent:
                    row = parent
                    text = row.inner_text()
                    if len(text) > 50:  # has enough content
                        break

            row_text = row.inner_text()
            p = _parse_structured_row(name, row_text, start_rank + len(players))
            players.append(p)
        except Exception:
            continue

    return players


def _parse_structured_row(name: str, text: str, rank: int) -> dict:
    """Parse a player row given we already know the name."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    nil_value = None
    ig = tik = tw = None
    class_year = None
    position = None
    school = None
    money_count = 0
    follower_count = 0

    for line in lines:
        if line == name:
            continue

        # NIL value: dollar sign present
        if "$" in line:
            v = parse_money(line)
            if v:
                nil_value = v
            continue

        # Followers: large numbers (likely K or M)
        if re.match(r"^[\d.]+[KkMm]?$", line):
            v = parse_followers(line)
            if v and v > 100:
                if ig is None:
                    ig = v
                elif tik is None:
                    tik = v
                elif tw is None:
                    tw = v
            continue

        # Class year keywords
        cy = normalize_class(line)
        if cy and class_year is None:
            class_year = cy
            continue

        # Position: short uppercase
        if re.match(r"^[A-Z]{1,5}(-[A-Z]{1,5})?$", line) and len(line) <= 6:
            if position is None:
                position = line

    return {
        "rank":               rank,
        "name":               name,
        "position":           position,
        "school":             school,
        "class_year":         class_year,
        "nil_value":          nil_value,
        "instagram_followers": ig,
        "tiktok_followers":   tik,
        "twitter_followers":  tw,
        "source":             "on3_dom",
    }


def _parse_rows_structured(page, page_num: int) -> list[dict]:
    """Last resort: parse the full page body text with smarter field detection."""
    content = page.inner_text("body")
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    players = []
    start_rank = (page_num - 1) * 25 + 1

    i = 0
    while i < len(lines):
        line = lines[i]
        # NIL values look like $X.XM or $XXXK — scan forward for player name
        if "$" in line and parse_money(line):
            nil = parse_money(line)
            # Search backwards from position i for the player name
            # The player name is a 2-3 word string without digits or parentheses
            for back in range(1, 15):
                if i - back < 0:
                    break
                candidate = lines[i - back]
                words = candidate.split()
                if (
                    2 <= len(words) <= 4
                    and not any(c.isdigit() for c in candidate)
                    and not candidate.startswith("(")
                    and not any(c in candidate for c in ["$", "%", "|", ","])
                    and candidate not in ("NIL Value", "Followers", "Instagram", "TikTok")
                    and candidate[0].isupper()
                ):
                    # Looks like a player name — check it's not a school/HS by ensuring
                    # no common school words
                    if not any(w in candidate.lower() for w in ["high", "school", "prep", "academy", "college", "university"]):
                        players.append({
                            "rank":               start_rank + len(players),
                            "name":               candidate,
                            "nil_value":          nil,
                            "position":           None,
                            "school":             None,
                            "class_year":         None,
                            "instagram_followers": None,
                            "tiktok_followers":   None,
                            "twitter_followers":  None,
                            "source":             "on3_text_fallback",
                        })
                        break
        i += 1

    return players


# ---------------------------------------------------------------------------
# Main scrape orchestrator
# ---------------------------------------------------------------------------

def scrape_on3(num_pages: int = 4) -> list[dict]:
    all_players = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        for page_num in range(1, num_pages + 1):
            url = BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"
            print(f"\nPage {page_num}: {url}")

            # Strategy 1: network interception
            players = scrape_via_network(page, url)
            strategy = "network"

            if not players:
                # Strategy 2: __NEXT_DATA__
                players = scrape_via_nextdata(page)
                strategy = "nextdata"

            if not players:
                # Strategy 3: DOM
                players = scrape_via_dom(page, page_num)
                strategy = "dom"

            if players:
                # Fix ranks for pagination
                offset = (page_num - 1) * 25
                for j, pp in enumerate(players):
                    if pp["rank"] <= 25 and page_num > 1:
                        pp["rank"] = offset + j + 1
                print(f"  [{strategy}] {len(players)} players | "
                      f"with NIL: {sum(1 for p in players if p.get('nil_value'))} | "
                      f"with social: {sum(1 for p in players if p.get('instagram_followers'))}")
                all_players.extend(players)
            else:
                print(f"  No players found on page {page_num}")

            time.sleep(2)

        browser.close()

    return all_players


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape On3 NIL rankings")
    parser.add_argument("--pages", type=int, default=4, help="Number of pages to scrape")
    args = parser.parse_args()

    print(f"Scraping {args.pages} pages from On3 NIL rankings...")
    players = scrape_on3(num_pages=args.pages)

    # Deduplicate — prefer (name, school) key; fall back to name-only when school absent
    seen = set()
    unique = []
    for p in players:
        name = (p.get("name") or "").lower().strip()
        school = (p.get("school") or "").lower().strip()
        key = (name, school) if school else (name, "")
        if name and key not in seen:
            seen.add(key)
            unique.append(p)
    unique.sort(key=lambda x: x.get("rank") or 9999)

    with_nil    = [p for p in unique if p.get("nil_value")]
    with_social = [p for p in unique if p.get("instagram_followers") or p.get("tiktok_followers")]

    print(f"\nTotal unique players: {len(unique)}")
    print(f"With NIL value:       {len(with_nil)}")
    print(f"With social data:     {len(with_social)}")

    out_path = os.path.abspath(OUTPUT_PATH)
    with open(out_path, "w") as f:
        json.dump(unique, f, indent=2)
    print(f"Saved → {out_path}")

    if with_nil:
        print("\nTop 10 by NIL value:")
        for p in sorted(with_nil, key=lambda x: x["nil_value"], reverse=True)[:10]:
            print(f"  #{p['rank']:>3} {p['name']:<30} {p.get('school','?'):<25} "
                  f"{p.get('position','?'):<5} ${p['nil_value']:>12,.0f}")


if __name__ == "__main__":
    main()
