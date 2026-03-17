import os
import sys
import requests
from dotenv import load_dotenv
from tqdm import tqdm
#THIS FILE IS FOR INGESTING CFB PLAYERS FROM COLLEGE FOOTBALL DATA API INTO THE DATABASE

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client

load_dotenv()

API_KEY = os.getenv("CFB_API_KEY")
BASE_URL = "https://api.collegefootballdata.com"

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

POWER4 = [
    "ACC",
    "SEC",
    "Big Ten",
    "Big 12"
]

def get_teams(year):
    url = f"{BASE_URL}/teams"
    params = {"year": year}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def get_roster(team, year):
    url = f"{BASE_URL}/roster"
    params = {"team": team, "year": year}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def ingest_year(year):
    teams = get_teams(year)
    power4_teams = [team for team in teams if team["conference"] in POWER4]
    
    print(f"🏈 Found {len(power4_teams)} Power 4 teams for {year}")
    print("⏳ Starting ingestion...\n")
    
    client = get_client()

    # Pre-load existing (name, school, season) to avoid duplicates
    print("Loading existing players from DB...")
    page_size = 1000; start = 0; existing_set = set()
    while True:
        r = client.table("players").select("name,school,season").range(start, start + page_size - 1).execute()
        rows = r.data or []
        if not rows: break
        for row in rows:
            existing_set.add((row["name"], row["school"], row.get("season")))
        if len(rows) < page_size: break
        start += page_size
    print(f"  {len(existing_set)} existing players loaded\n")

    players_added = 0
    players_skipped = 0
    players_failed = 0
    batch = []

    for team in tqdm(power4_teams, desc="Collecting rosters", unit="team"):
        try:
            roster = get_roster(team["school"], year)
            for player in roster:
                name = (player.get("firstName", "") + " " + player.get("lastName", "")).strip()
                school = team.get("school")
                key = (name, school, year)
                if key in existing_set:
                    players_skipped += 1
                    continue
                batch.append({
                    "name": name,
                    "position": player.get("position"),
                    "school": school,
                    "conference": team.get("conference"),
                    "season": year,
                })
                existing_set.add(key)
        except Exception as e:
            print(f"\n⚠️  Error fetching roster for {team['school']}: {e}")

    # Bulk insert in batches of 500
    print(f"\nInserting {len(batch)} new players...")
    insert_batch_size = 500
    for i in range(0, len(batch), insert_batch_size):
        chunk = batch[i:i + insert_batch_size]
        try:
            client.table("players").insert(chunk).execute()
            players_added += len(chunk)
        except Exception as e:
            # Fall back to one-by-one on error
            for p in chunk:
                try:
                    client.table("players").insert(p).execute()
                    players_added += 1
                except:
                    players_failed += 1

    print(f"\n✅ {year} ingestion complete!")
    print(f"  ✓ Added:   {players_added} players")
    print(f"  ↷ Skipped: {players_skipped} already exist")
    print(f"  ✗ Failed:  {players_failed} players")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest CFB player rosters into Supabase")
    parser.add_argument("--year", type=int, default=2023, help="Season year to ingest")
    args = parser.parse_args()
    ingest_year(args.year)
