import os
import sys
import requests
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm
#THIS FILE IS FOR INGESTING CFB PLAYERS FROM COLLEGE FOOTBALL DATA API INTO THE DATABASE

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.crud import create_player
from db.models import PlayerCreate

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
    
    players_added = 0
    players_failed = 0

    for team in tqdm(power4_teams, desc="Ingesting teams", unit="team"):
        try:
            roster = get_roster(team["school"], year)

            for player in roster:
                try:
                    new_player = PlayerCreate(
                        name=player.get("firstName", "") + " " + player.get("lastName", ""),
                        position=player.get("position"),
                        school=team.get("school"),
                        conference=team.get("conference")
                    )
                    create_player(new_player)
                    players_added += 1
                except Exception as e:
                    players_failed += 1
        except Exception as e:
            print(f"\n⚠️  Error fetching roster for {team['school']}: {e}")

    print(f"\n✅ {year} ingestion complete!")
    print(f"  ✓ Added: {players_added} players")
    print(f"  ✗ Failed: {players_failed} players")

if __name__ == "__main__":
    ingest_year(2023)
