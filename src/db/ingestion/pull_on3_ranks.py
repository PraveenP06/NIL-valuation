"""
Scrape On3 roster pages to get each player's NIL rank (free, even without subscription).
Apply a power-law curve (fit from the top-27 football leaderboard) to estimate NIL values.
Writes results to data/on3_rank_labels.json for use as soft labels in calibration.

Usage:
    python src/db/ingestion/pull_on3_ranks.py
    python src/db/ingestion/pull_on3_ranks.py --max-schools 10   # test run
"""
import os, sys, re, json, time, argparse
import requests
import numpy as np
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from dotenv import load_dotenv
load_dotenv()

DATA_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../data'))
OUT_PATH  = os.path.join(DATA_DIR, 'on3_rank_labels.json')

REQUEST_DELAY = 1.5   # seconds between roster page requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

# ---------------------------------------------------------------------------
# Power-law curve fit from On3 top-27 football leaderboard
# value = A * rank ^ B  (fit error: ~3% on training range)
# ---------------------------------------------------------------------------
POWER_A =  5_676_617.0
POWER_B = -0.3357

def rank_to_value(rank: int) -> float:
    return round(POWER_A * (rank ** POWER_B))


# ---------------------------------------------------------------------------
# On3 slug mapping — DB school name → On3 URL slug
# ---------------------------------------------------------------------------
SCHOOL_SLUGS = {
    "Alabama":           "alabama-crimson-tide",
    "Arizona":           "arizona-wildcats",
    "Arizona State":     "arizona-state-sun-devils",
    "Arkansas":          "arkansas-razorbacks",
    "Auburn":            "auburn-tigers",
    "Baylor":            "baylor-bears",
    "Boston College":    "boston-college-eagles",
    "California":        "california-golden-bears",
    "Clemson":           "clemson-tigers",
    "Colorado":          "colorado-buffaloes",
    "Duke":              "duke-blue-devils",
    "Florida":           "florida-gators",
    "Florida State":     "florida-state-seminoles",
    "Georgia":           "georgia-bulldogs",
    "Georgia Tech":      "georgia-tech-yellow-jackets",
    "Illinois":          "illinois-fighting-illini",
    "Indiana":           "indiana-hoosiers",
    "Iowa":              "iowa-hawkeyes",
    "Iowa State":        "iowa-state-cyclones",
    "Kansas":            "kansas-jayhawks",
    "Kansas State":      "kansas-state-wildcats",
    "Kentucky":          "kentucky-wildcats",
    "Louisville":        "louisville-cardinals",
    "LSU":               "lsu-tigers",
    "Maryland":          "maryland-terrapins",
    "Miami":             "miami-hurricanes",
    "Michigan":          "michigan-wolverines",
    "Michigan State":    "michigan-state-spartans",
    "Minnesota":         "minnesota-golden-gophers",
    "Mississippi State": "mississippi-state-bulldogs",
    "Missouri":          "missouri-tigers",
    "NC State":          "nc-state-wolfpack",
    "Nebraska":          "nebraska-cornhuskers",
    "North Carolina":    "north-carolina-tar-heels",
    "Northwestern":      "northwestern-wildcats",
    "Notre Dame":        "notre-dame-fighting-irish",
    "Ohio State":        "ohio-state-buckeyes",
    "Oklahoma":          "oklahoma-sooners",
    "Oklahoma State":    "oklahoma-state-cowboys",
    "Ole Miss":          "ole-miss-rebels",
    "Oregon":            "oregon-ducks",
    "Oregon State":      "oregon-state-beavers",
    "Penn State":        "penn-state-nittany-lions",
    "Pittsburgh":        "pittsburgh-panthers",
    "Purdue":            "purdue-boilermakers",
    "Rutgers":           "rutgers-scarlet-knights",
    "SMU":               "smu-mustangs",
    "South Carolina":    "south-carolina-gamecocks",
    "Stanford":          "stanford-cardinal",
    "Syracuse":          "syracuse-orange",
    "TCU":               "tcu-horned-frogs",
    "Tennessee":         "tennessee-volunteers",
    "Texas":             "texas-longhorns",
    "Texas A&M":         "texas-am-aggies",
    "Texas Tech":        "texas-tech-red-raiders",
    "UCLA":              "ucla-bruins",
    "USC":               "usc-trojans",
    "Utah":              "utah-utes",
    "Vanderbilt":        "vanderbilt-commodores",
    "Virginia":          "virginia-cavaliers",
    "Virginia Tech":     "virginia-tech-hokies",
    "Wake Forest":       "wake-forest-demon-deacons",
    "Washington":        "washington-huskies",
    "Washington State":  "washington-state-cougars",
    "West Virginia":     "west-virginia-mountaineers",
    "Wisconsin":         "wisconsin-badgers",
    "Houston":           "houston-cougars",
    "UCF":               "ucf-knights",
    "Cincinnati":        "cincinnati-bearcats",
}


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())


def scrape_roster(school: str, slug: str, year: int = 2025) -> list[dict]:
    """Fetch On3 roster page and return list of {name, position, rank, group_rank}."""
    url = f"https://www.on3.com/college/{slug}/football/{year}/roster/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", r.text, re.DOTALL)
        for s in scripts:
            if len(s) > 5000:
                try:
                    data = json.loads(s.strip())
                    players = data["props"]["pageProps"]["rosterList"]["list"]
                    results = []
                    for p in players:
                        player = p.get("player", {})
                        name   = player.get("fullName", "")
                        pos    = (p.get("rosterRating") or p.get("rating") or {}).get("positionAbbr", "")
                        nil_v  = p.get("nilValue") or {}
                        rank   = nil_v.get("rank")
                        grp    = nil_v.get("groupRank")   # sport-specific rank
                        if name:
                            results.append({
                                "name":       name,
                                "school":     school,
                                "position":   pos or "",
                                "rank":       rank,
                                "group_rank": grp,
                            })
                    return results
                except:
                    pass
    except Exception as e:
        tqdm.write(f"  Error scraping {school}: {e}")
    return []


def main(max_schools: int | None = None):
    schools = list(SCHOOL_SLUGS.items())
    if max_schools:
        schools = schools[:max_schools]

    print(f"Scraping On3 roster ranks for {len(schools)} schools...")
    print(f"Power law: value = {POWER_A:,.0f} × rank^{POWER_B:.4f}")
    print()

    all_entries = []
    total_ranked = 0

    for school, slug in tqdm(schools, desc="Schools", unit="school"):
        players = scrape_roster(school, slug)
        ranked  = [p for p in players if p["rank"] is not None]
        total_ranked += len(ranked)

        for p in ranked:
            # Use group_rank (sport-specific) if available, else global rank
            rank = p["group_rank"] or p["rank"]
            est_value = rank_to_value(rank)
            all_entries.append({
                "name":      p["name"],
                "school":    school,
                "position":  p["position"],
                "rank":      rank,
                "nil_value": est_value,
                "source":    "on3_rank_estimate",
            })

        tqdm.write(f"  {school}: {len(players)} players, {len(ranked)} ranked")
        time.sleep(REQUEST_DELAY)

    # Sort by rank (best first)
    all_entries.sort(key=lambda x: x["rank"])

    with open(OUT_PATH, "w") as f:
        json.dump(all_entries, f, indent=2)

    print(f"\nDone.")
    print(f"  Total players scraped : {sum(1 for _ in all_entries) + (total_ranked - len(all_entries))}")
    print(f"  Players with ranks    : {len(all_entries)}")
    print(f"  Saved → {OUT_PATH}")

    # Show value distribution
    vals = [e["nil_value"] for e in all_entries]
    if vals:
        print(f"\n  Estimated value distribution:")
        for lo, hi in [(0,300_000),(300_000,700_000),(700_000,1_500_000),(1_500_000,999_999_999)]:
            count = sum(1 for v in vals if lo <= v < hi)
            label = f"${lo//1000:,}K–${hi//1000:,}K" if hi < 999_999_999 else f">${lo//1000:,}K"
            print(f"    {label:<20} {count} players")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-schools", type=int, default=None)
    args = parser.parse_args()
    main(max_schools=args.max_schools)
