import os
import sys
import requests
import argparse
import re
from collections import defaultdict
from dotenv import load_dotenv
from tqdm import tqdm

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.crud import get_all_players
from db.connection import get_client

load_dotenv()

API_KEY = os.getenv("CFB_API_KEY")
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

def get_player_stats(year):
    """Fetch player statistics from CFB API"""
    url = f"{BASE_URL}/stats/player/season"
    params = {"year": year}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"API Error: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        raise Exception(f"API returned {response.status_code}")
    return response.json()

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

        stat_type = (row.get("statType") or "").upper()
        stat_value_raw = row.get("stat")
        try:
            stat_value = float(stat_value_raw)
        except (TypeError, ValueError):
            stat_value = 0.0

        entry = aggregated[key]
        if stat_type in {"YDS", "PASS_YDS", "RUSH_YDS", "REC_YDS", "TOT_YDS"}:
            entry["total_yards"] += stat_value
        elif stat_type in {"TD", "PASS_TD", "RUSH_TD", "REC_TD", "TOT_TD"}:
            entry["touchdowns"] += int(stat_value)
        elif stat_type in {"ATT", "PASS_ATT", "RUSH_ATT"}:
            entry["attempts"] += int(stat_value)
        elif stat_type in {"G", "GP", "GAMES"}:
            entry["games_played"] = max(entry["games_played"], int(stat_value))

    print(f"🔎 Aggregated into {len(aggregated)} player-team stat profiles")
    
    stats_added = 0
    stats_failed = 0
    
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
