import os
import sys
import requests
import argparse
import re
import time
from collections import defaultdict
from dotenv import load_dotenv
from tqdm import tqdm

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.crud import get_all_players
from db.connection import get_client

load_dotenv()

API_KEY = os.getenv("CFB_API_KEY")
if not API_KEY:
    raise RuntimeError("CFB_API_KEY is not set. Add it to your .env file.")
BASE_URL = "https://api.collegefootballdata.com"

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

client = get_client()


def normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = value.lower().strip()
    normalized = normalized.replace("&", "and")
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_player_name(name: str) -> str:
    cleaned = normalize_text(name)
    tokens = [t for t in cleaned.split(" ") if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(tokens)

def get_player_stats(year, max_retries=5, timeout=45):
    """Fetch player statistics from CFB API with retry for transient network errors"""
    url = f"{BASE_URL}/stats/player/season"
    params = {"year": year}

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            if response.status_code != 200:
                print(f"API Error: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                raise Exception(f"API returned {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as error:
            last_error = error
            if attempt == max_retries:
                break
            wait_seconds = min(2 ** attempt, 20)
            print(f"⚠️  Request failed (attempt {attempt}/{max_retries}). Retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)

    raise Exception(f"Failed after {max_retries} attempts: {last_error}")

def ingest_performance_stats(year, max_rows=None):
    """Ingest performance stats for all players in database"""
    print(f"🏈 Fetching performance stats for {year}...\n")
    
    # Get all stats from API
    try:
        all_stats = get_player_stats(year)
        if max_rows:
            all_stats = all_stats[:max_rows]
        print(f"✅ Retrieved {len(all_stats)} player stat records from API")
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")
        return
    
    # Get all players from database
    players = get_all_players()
    print(f"📊 Found {len(players)} players in database\n")

    # Build fast lookup maps for matching
    players_by_name_school = {}
    players_by_name_only = defaultdict(list)

    for player in players:
        name_key = normalize_player_name(player.name or "")
        school_key = normalize_text(player.school or "")
        if name_key and school_key:
            existing = players_by_name_school.get((name_key, school_key))
            # Prefer the player record whose season matches the ingestion year
            if not existing or player.season == year:
                players_by_name_school[(name_key, school_key)] = player
        if name_key:
            players_by_name_only[name_key].append(player)

    # API is flat rows (one row per statType/category) - aggregate per player/team first
    aggregated = {}
    for row in all_stats:
        player_name = row.get("player", "")
        player_team = row.get("team", "")
        key = (normalize_player_name(player_name), normalize_text(player_team))
        if not key[0]:
            continue

        if key not in aggregated:
            aggregated[key] = {
                "player_name": player_name,
                "player_team": player_team,
                "total_yards": 0.0,
                "touchdowns": 0,
                "attempts": 0,
                "games_played": 0,
            }

        stat_type = (row.get("statType") or "").upper().strip()
        category = (row.get("category") or "").lower()  # e.g. "passing", "rushing", "receiving"
        stat_value_raw = row.get("stat")
        try:
            stat_value = float(stat_value_raw)
        except (TypeError, ValueError):
            stat_value = 0.0

        entry = aggregated[key]
        offensive = category in {"passing", "rushing", "receiving"}
        defensive = category == "defensive"

        if stat_type == "YDS" and offensive:
            entry["total_yards"] += stat_value
        elif stat_type == "TD" and offensive:
            entry["touchdowns"] += int(stat_value)
        elif stat_type in {"ATT", "CAR", "COMPLETIONS"} and offensive:
            entry["attempts"] += int(stat_value)
        elif stat_type in {"G", "GP", "GAMES"}:
            entry["games_played"] = max(entry["games_played"], int(stat_value))
        # Defensive stats → production equivalent stored in total_yards
        # Weights chosen so a solid starter (~80 tackles, 3 sacks) ≈ 500 units,
        # comparable to a WR with 400-500 receiving yards. Position-percentile
        # normalization in model.py keeps defenders ranked against defenders only.
        elif defensive and stat_type in {"TOT", "TACKLES"}:
            entry["def_tackles"] = entry.get("def_tackles", 0.0) + stat_value
        elif defensive and stat_type == "SOLO":
            entry["def_solo"] = entry.get("def_solo", 0.0) + stat_value
        elif defensive and stat_type in {"SACKS", "SACK"}:
            entry["def_sacks"] = entry.get("def_sacks", 0.0) + stat_value
        elif defensive and stat_type in {"TFL", "TFLS", "TFL-YDS"}:
            entry["def_tfl"] = entry.get("def_tfl", 0.0) + stat_value
        elif defensive and stat_type in {"INT", "INTS"}:
            entry["def_int"] = entry.get("def_int", 0.0) + stat_value
        elif defensive and stat_type in {"PD", "PBU", "PASS BREAKUPS"}:
            entry["def_pd"] = entry.get("def_pd", 0.0) + stat_value

    print(f"🔎 Aggregated into {len(aggregated)} player-team stat profiles")

    # Match aggregated stats to players in database
    stats_added = 0
    stats_updated = 0
    stats_failed = 0
    unmatched = 0

    for (name_key, school_key), data in tqdm(aggregated.items(), desc="Processing players", unit="player"):
        try:
            # Primary match by (name, school), fallback to unique name-only
            matching_player = players_by_name_school.get((name_key, school_key))
            if not matching_player:
                candidates = players_by_name_only.get(name_key, [])
                if len(candidates) == 1:
                    matching_player = candidates[0]
            
            if not matching_player:
                unmatched += 1
                continue

            total_yards = data["total_yards"]
            total_tds = data["touchdowns"]
            total_attempts = data["attempts"]
            games_played = data["games_played"]

            # Compute defensive production equivalent
            def_tackles = data.get("def_tackles", 0.0) or data.get("def_solo", 0.0)
            def_sacks    = data.get("def_sacks", 0.0)
            def_tfl      = data.get("def_tfl", 0.0)
            def_int      = data.get("def_int", 0.0)
            def_pd       = data.get("def_pd", 0.0)
            def_prod = (def_tackles * 5.0 + def_sacks * 40.0 +
                        def_tfl * 15.0 + def_int * 60.0 + def_pd * 12.0)

            has_offense = total_yards > 0 or total_tds > 0 or total_attempts > 0
            has_defense = def_prod > 0

            # Skip players with no meaningful stats of any kind
            if not has_offense and not has_defense:
                unmatched += 1
                continue

            # For purely defensive players, store def_prod as total_yards
            if not has_offense and has_defense:
                total_yards = def_prod
                total_tds = 0
                total_attempts = 0

            yards_per_game = (total_yards / games_played) if games_played > 0 else None
            efficiency_metric = (total_yards / total_attempts) if total_attempts > 0 else None

            payload = {
                "player_id": matching_player.id,
                "season": year,
                "player_name": matching_player.name,
                "school": matching_player.school,
                "total_yards": float(total_yards) if total_yards else None,
                "touchdowns": int(total_tds) if total_tds else None,
                "attempts": int(total_attempts) if total_attempts else None,
                "yards_per_game": float(yards_per_game) if yards_per_game is not None else None,
                "efficiency_metric": float(efficiency_metric) if efficiency_metric is not None else None,
                "usage_share": None,
                "team_wins": None,
            }

            existing = client.table("performance_stats").select("id").eq("player_id", matching_player.id).eq("season", year).limit(1).execute().data
            client.table("performance_stats").upsert(payload, on_conflict="player_id,season").execute()
            if existing:
                stats_updated += 1
            else:
                stats_added += 1
            
        except Exception as e:
            stats_failed += 1
            continue
    
    print(f"\n✅ Performance stats ingestion complete!")
    print(f"  ✓ Added: {stats_added} stat records")
    print(f"  ↻ Updated: {stats_updated} stat records")
    print(f"  ⊘ Unmatched: {unmatched} player profiles")
    print(f"  ✗ Failed: {stats_failed} records")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest CFB player performance stats into Supabase")
    parser.add_argument("--year", type=int, default=2023, help="Season year to ingest")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional cap for API rows (debug/testing)")
    args = parser.parse_args()

    ingest_performance_stats(args.year, max_rows=args.max_rows)
