"""
Pull class year (FR/SO/JR/SR) for 2023 players from the CFBD roster API
and mark 2024 NFL draft picks in the players table.

Usage:
    python src/db/ingestion/pull_cfb_class_year.py
    python src/db/ingestion/pull_cfb_class_year.py --dry-run
"""
import os
import sys
import re
import time
import argparse
import requests
from dotenv import load_dotenv
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_client

load_dotenv()

API_KEY  = os.getenv("CFB_API_KEY")
BASE_URL = "https://api.collegefootballdata.com"
HEADERS  = {"Authorization": f"Bearer {API_KEY}"}

# ---------------------------------------------------------------------------
# 2024 NFL Draft picks — used to mark nfl_drafted_2024 = true
# ---------------------------------------------------------------------------

NFL_DRAFT_2024 = [
    ("Caleb Williams", "USC"), ("Jayden Daniels", "LSU"), ("Drake Maye", "North Carolina"),
    ("Marvin Harrison Jr", "Ohio State"), ("Joe Alt", "Notre Dame"), ("Malik Nabers", "LSU"),
    ("JC Latham", "Alabama"), ("Michael Penix Jr", "Washington"), ("Rome Odunze", "Washington"),
    ("J.J. McCarthy", "Michigan"), ("Olumuyiwa Fashanu", "Penn State"), ("Bo Nix", "Oregon"),
    ("Brock Bowers", "Georgia"), ("Taliese Fuaga", "Oregon State"), ("Laiatu Latu", "UCLA"),
    ("Byron Murphy II", "Texas"), ("Dallas Turner", "Alabama"), ("Amarius Mims", "Georgia"),
    ("Jared Verse", "Florida State"), ("Troy Fautanu", "Washington"), ("Chop Robinson", "Penn State"),
    ("Quinyon Mitchell", "Toledo"), ("Brian Thomas Jr", "LSU"), ("Terrion Arnold", "Alabama"),
    ("Jordan Morgan", "Arizona"), ("Graham Barton", "Duke"), ("Darius Robinson", "Missouri"),
    ("Xavier Worthy", "Texas"), ("Tyler Guyton", "Oklahoma"), ("Nate Wiggins", "Clemson"),
    ("Ricky Pearsall", "Florida"), ("Xavier Legette", "South Carolina"), ("Keon Coleman", "Florida State"),
    ("Ladd McConkey", "Georgia"), ("Ruke Orhorhoro", "Clemson"), ("Jer'zhan Newton", "Illinois"),
    ("Ja'Lynn Polk", "Washington"), ("T'Vondre Sweat", "Texas"), ("Braden Fiske", "Florida State"),
    ("Cooper DeJean", "Iowa"), ("Kool-Aid McKinstry", "Alabama"), ("Kamari Lassiter", "Georgia"),
    ("Max Melton", "Rutgers"), ("Jackson Powers-Johnson", "Oregon"), ("Edgerrin Cooper", "Texas A&M"),
    ("Jonathon Brooks", "Texas"), ("Tyler Nubin", "Minnesota"), ("Maason Smith", "LSU"),
    ("Kris Jenkins", "Michigan"), ("Mike Sainristil", "Michigan"), ("Zach Frazier", "West Virginia"),
    ("Adonai Mitchell", "Texas"), ("Ben Sinnott", "Kansas State"), ("Michael Hall Jr", "Ohio State"),
    ("Patrick Paul", "Houston"), ("Marshawn Kneeland", "Western Michigan"), ("Chris Braswell", "Alabama"),
    ("Javon Bullard", "Georgia"), ("Blake Fisher", "Notre Dame"), ("Cole Bishop", "Utah"),
    ("Ennis Rakestraw Jr", "Missouri"), ("Roger Rosengarten", "Washington"), ("Kingsley Suamataia", "BYU"),
    ("Renardo Green", "Florida State"), ("Malachi Corley", "Western Kentucky"), ("Trey Benson", "Florida State"),
    ("Brandon Coleman", "TCU"), ("Caedan Wallace", "Penn State"), ("Junior Colson", "Michigan"),
    ("Andru Phillips", "Kentucky"), ("Isaiah Adams", "Illinois"), ("Trevin Wallace", "Kentucky"),
    ("Cooper Beebe", "Kansas State"), ("Bralen Trice", "Washington"), ("Jonah Elliss", "Utah"),
    ("Calen Bullock", "USC"), ("Jermaine Burton", "Alabama"), ("Christian Haynes", "Connecticut"),
    ("Blake Corum", "Michigan"), ("Roman Wilson", "Michigan"), ("Zak Zinter", "Michigan"),
    ("Dominick Puni", "Kansas"), ("Marist Liufau", "Notre Dame"), ("MarShawn Lloyd", "USC"),
    ("Tykee Smith", "Georgia"), ("Elijah Jones", "Boston College"), ("Ty'Ron Hopper", "Missouri"),
    ("Jalen McMillan", "Washington"), ("Adisa Isaac", "Penn State"), ("Jalyx Hunt", "Houston Christian"),
    ("DeWayne Carter", "Duke"), ("Jarrian Jones", "Florida State"), ("McKinnley Jackson", "Texas A&M"),
    ("Payton Wilson", "North Carolina State"), ("Kamren Kinchens", "Miami"), ("Luke McCaffrey", "Rice"),
    ("Ja'Tavion Sanders", "Texas"), ("Troy Franklin", "Oregon"), ("Layden Robinson", "Texas A&M"),
    ("Dadrion Taylor-Demerson", "Texas Tech"), ("Justin Eboigbe", "Alabama"), ("Cedric Gray", "North Carolina"),
    ("Theo Johnson", "Penn State"), ("Khyree Jackson", "Oregon"), ("Javon Baker", "UCF"),
    ("Evan Williams", "Oregon"), ("Decamerion Richardson", "Mississippi State"), ("Devontez Walker", "North Carolina"),
    ("Javon Foster", "Missouri"), ("Erick All", "Iowa"), ("Jordan Jefferson", "LSU"),
    ("Tanor Bortolini", "Wisconsin"), ("Jaylen Wright", "Tennessee"), ("A.J. Barner", "Michigan"),
    ("Cade Stover", "Ohio State"), ("Malik Mustapha", "Wake Forest"), ("Bucky Irving", "Oregon"),
    ("Will Shipley", "Clemson"), ("Ray Davis", "Kentucky"), ("Isaac Guerendo", "Louisville"),
    ("T.J. Tampa", "Iowa State"), ("Jared Wiley", "TCU"), ("Sione Vaki", "Utah"),
    ("Jaden Hicks", "Washington State"), ("Braelon Allen", "Wisconsin"), ("Jacob Cowing", "Arizona"),
    ("Nehemiah Pritchett", "Auburn"), ("Tarheeb Still", "Maryland"), ("Xavier Thomas", "Clemson"),
    ("Cam Hart", "Notre Dame"), ("Sedrick Van Pran-Granger", "Georgia"), ("Anthony Gould", "Oregon State"),
    ("JD Bertrand", "Notre Dame"), ("Austin Booker", "Kansas"), ("Kris Abrams-Draine", "Missouri"),
    ("Jarvis Brownlee Jr", "Louisville"), ("Audric Estime", "Notre Dame"), ("Tommy Eichenberg", "Ohio State"),
    ("Josh Newton", "TCU"), ("Spencer Rattler", "South Carolina"), ("Jaylon Carlies", "Missouri"),
    ("Ainias Smith", "Texas A&M"), ("Deantre Prince", "Mississippi"), ("Brennan Jackson", "Washington State"),
    ("Jeremiah Trotter Jr", "Clemson"), ("Jamari Thrash", "Louisville"), ("Chau Smith-Wade", "Washington State"),
    ("Mohamed Kamara", "Colorado State"), ("Jaylen Harrell", "Michigan"), ("Tatum Bethune", "Florida State"),
    ("Jase McClellan", "Alabama"), ("Casey Washington", "Illinois"), ("Jamal Hill", "Oregon"),
    ("Mekhi Wingo", "LSU"), ("Dylan McMahon", "North Carolina State"), ("DJ James", "Auburn"),
    ("Joe Milton III", "Tennessee"), ("Tanner McLachlan", "Arizona"), ("Ryan Watts", "Texas"),
    ("Tyler Davis", "Clemson"), ("Zion Logue", "Georgia"), ("Patrick McMorris", "California"),
    ("Jaden Crumedy", "Mississippi State"), ("Will Reichard", "Alabama"), ("Jawhar Jordan", "Louisville"),
    ("Nathaniel Watson", "Mississippi State"), ("Jordan Whittington", "Texas"), ("Cedric Johnson", "Mississippi"),
    ("Beaux Limmer", "Arkansas"), ("Devin Leary", "Kentucky"), ("Daequan Hardy", "Penn State"),
    ("Jaylin Simpson", "Auburn"), ("Rasheen Ali", "Marshall"), ("Tyrone Tracy Jr", "Purdue"),
    ("Javon Solomon", "Troy"), ("Bub Means", "Pittsburgh"), ("Jordan Travis", "Florida State"),
    ("Isaiah Davis", "South Dakota State"), ("Caelen Carson", "Wake Forest"), ("Jaylan Ford", "Texas"),
    ("Kamal Hadden", "Tennessee"), ("Cam Little", "Arkansas"), ("Cornelius Johnson", "Michigan"),
    ("Kalen King", "Penn State"), ("Michael Barrett", "Michigan"), ("LaDarius Henderson", "Michigan"),
    ("Tahj Washington", "USC"), ("Brenden Rice", "USC"),
]

# Normalised (lowercase, no punctuation) for fuzzy matching
def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    # Strip common suffixes
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())

NFL_DRAFT_NORM = {(_norm(name), _norm(school)) for name, school in NFL_DRAFT_2024}
NFL_DRAFT_NAMES = {_norm(name) for name, _ in NFL_DRAFT_2024}


# ---------------------------------------------------------------------------
# CFBD API helpers
# ---------------------------------------------------------------------------

POWER4 = {"ACC", "SEC", "Big Ten", "Big 12"}

def get_teams(year: int) -> list[dict]:
    r = requests.get(f"{BASE_URL}/teams", headers=HEADERS, params={"year": year})
    r.raise_for_status()
    return r.json()

def get_roster(team: str, year: int) -> list[dict]:
    r = requests.get(f"{BASE_URL}/roster", headers=HEADERS, params={"team": team, "year": year})
    if r.status_code != 200:
        return []
    return r.json() or []

YEAR_MAP = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}  # 5th-year → senior


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Backfill class_year and nfl_drafted_2024 for players")
    parser.add_argument("--year", type=int, default=2023, help="Season year to backfill (default: 2023)")
    parser.add_argument("--dry-run", action="store_true", help="Print updates without writing to DB")
    args = parser.parse_args()

    client = get_client()

    # --- Step 1: Load players from DB for this season ---
    print(f"Loading {args.year} players from DB...")
    page_size, start, db_players = 1000, 0, []
    while True:
        batch = client.table("players").select("id,name,school,season").eq("season", args.year).range(start, start + page_size - 1).execute().data or []
        db_players.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    print(f"  {len(db_players)} players loaded")

    # Build lookup: (norm_name, norm_school) → player_id
    db_lookup: dict[tuple, int] = {}
    db_name_only: dict[str, list[int]] = {}
    for p in db_players:
        key = (_norm(p["name"]), _norm(p["school"] or ""))
        db_lookup[key] = p["id"]
        db_name_only.setdefault(_norm(p["name"]), []).append(p["id"])

    # --- Step 2: Fetch CFBD rosters for all Power 4 teams ---
    print(f"\nFetching CFBD rosters for {args.year}...")
    teams = get_teams(args.year)
    p4_teams = [t for t in teams if t.get("conference") in POWER4]
    print(f"  {len(p4_teams)} Power 4 teams")

    # roster_map: player_id → class_year int
    class_year_updates: dict[int, int] = {}
    matched = unmatched = 0

    for team in tqdm(p4_teams, desc="Fetching rosters", unit="team"):
        roster = get_roster(team["school"], args.year)
        time.sleep(0.1)  # gentle rate limit
        for r in roster:
            first = r.get("firstName") or ""
            last  = r.get("lastName") or ""
            full  = f"{first} {last}".strip()
            yr    = r.get("year")
            if not full or yr is None:
                continue
            class_yr = YEAR_MAP.get(int(yr)) if yr else None
            if class_yr is None:
                continue

            norm_name   = _norm(full)
            norm_school = _norm(team["school"])
            pid = db_lookup.get((norm_name, norm_school))

            if pid is None:
                # Fallback: unique name match
                candidates = db_name_only.get(norm_name, [])
                if len(candidates) == 1:
                    pid = candidates[0]

            if pid:
                class_year_updates[pid] = class_yr
                matched += 1
            else:
                unmatched += 1

    print(f"  Matched: {matched} | Unmatched: {unmatched}")

    # --- Step 3: Mark NFL draft picks ---
    print("\nMarking 2024 NFL draft picks...")
    draft_pids: list[int] = []
    for p in db_players:
        norm_name   = _norm(p["name"])
        norm_school = _norm(p["school"] or "")
        if (norm_name, norm_school) in NFL_DRAFT_NORM or norm_name in NFL_DRAFT_NAMES:
            draft_pids.append(p["id"])
    print(f"  Found {len(draft_pids)} draft picks in DB")

    # --- Step 4: Write updates ---
    if args.dry_run:
        print(f"\n[DRY RUN] Would update class_year for {len(class_year_updates)} players")
        print(f"[DRY RUN] Would mark nfl_drafted_2024=true for {len(draft_pids)} players")
        return

    print(f"\nWriting class_year updates ({len(class_year_updates)} players)...")
    batch_size = 50
    updated_cy = 0
    items = list(class_year_updates.items())
    for i in tqdm(range(0, len(items), batch_size), desc="Updating class_year"):
        chunk = items[i:i + batch_size]
        for pid, cy in chunk:
            try:
                client.table("players").update({"class_year": cy}).eq("id", pid).execute()
                updated_cy += 1
            except Exception as e:
                tqdm.write(f"  Error updating player {pid}: {e}")

    print(f"Writing nfl_drafted_2024 flags ({len(draft_pids)} players)...")
    updated_nfl = 0
    for pid in tqdm(draft_pids, desc="Marking NFL drafts"):
        try:
            client.table("players").update({"nfl_drafted_2024": True}).eq("id", pid).execute()
            updated_nfl += 1
        except Exception as e:
            tqdm.write(f"  Error marking draft pick {pid}: {e}")

    print(f"\n✅ Done!")
    print(f"  class_year updated: {updated_cy}")
    print(f"  nfl_drafted_2024:   {updated_nfl}")

    # Quick distribution check
    dist = {}
    for cy in class_year_updates.values():
        dist[cy] = dist.get(cy, 0) + 1
    print(f"\n  Class year distribution: {dict(sorted(dist.items()))}")
    print(f"  (1=FR, 2=SO, 3=JR, 4=SR)")


if __name__ == "__main__":
    main()
