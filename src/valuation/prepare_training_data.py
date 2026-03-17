"""
Build the ML training dataset for the NIL valuation model.

Steps:
  1. Load On3 rankings from data/on3_rankings.json
  2. Fit a power-law curve to rank → NIL value using the top-28 labeled points
  3. Extrapolate NIL values for ranks 29–100+
  4. Pull all 2023 players + features from the DB
  5. Match On3 players to DB players (by name + school)
  6. Build feature matrix X and target vector y
  7. Save train.csv and test.csv to data/

Usage:
    python src/valuation/prepare_training_data.py
    python src/valuation/prepare_training_data.py --test-size 0.2 --min-nil 1000
"""
import os
import sys
import re
import json
import argparse
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from sklearn.model_selection import train_test_split

from db.connection import get_client
from db.crud import get_all_players, get_all_performance_stats_by_season, get_all_social_media
from valuation.model import (
    calculate_school_score,
    get_position_multiplier,
    get_conference_multiplier,
    TIER1_SCHOOLS,
    TIER2_SCHOOLS,
)

DATA_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
ON3_PATH    = os.path.join(DATA_DIR, "on3_rankings.json")
SUPPL_PATH  = os.path.join(DATA_DIR, "nil_supplement.json")
TRAIN_PATH  = os.path.join(DATA_DIR, "train.csv")
TEST_PATH   = os.path.join(DATA_DIR, "test.csv")
LABELS_PATH = os.path.join(DATA_DIR, "nil_labels.csv")

# High school / non-player strings that leak from On3 scrape
HS_KEYWORDS = {"high", "school", "prep", "academy", "little elm", "archbishop",
               "forest hills", "isidore", "west linn", "lake dallas",
               "martin luther king", "south florence", "st joseph", "chaminade"}


# ---------------------------------------------------------------------------
# Step 1 — Power-law curve fitting
# ---------------------------------------------------------------------------

def power_law(rank: np.ndarray, a: float, b: float) -> np.ndarray:
    """NIL ≈ a * rank^b  (b < 0 for decay)"""
    return a * np.power(rank, b)


def fit_rank_curve(on3_players: list[dict]) -> tuple[float, float] | None:
    """Fit power-law to labeled On3 data. Returns (a, b) or None."""
    labeled = [(p["rank"], p["nil_value"]) for p in on3_players if p.get("nil_value") and p.get("rank")]
    if len(labeled) < 5:
        print(f"  Only {len(labeled)} labeled points — cannot fit curve reliably.")
        return None

    labeled.sort(key=lambda x: x[0])
    ranks  = np.array([x[0] for x in labeled], dtype=float)
    values = np.array([x[1] for x in labeled], dtype=float)

    try:
        popt, _ = curve_fit(power_law, ranks, values, p0=[5_000_000, -0.8], maxfev=10000)
        a, b = popt
        print(f"  Curve fit: NIL ≈ ${a:,.0f} × rank^{b:.3f}")
        # Sanity check
        pred_rank1  = power_law(np.array([1.0]), a, b)[0]
        pred_rank50 = power_law(np.array([50.0]), a, b)[0]
        print(f"  Predicted rank 1: ${pred_rank1:,.0f} | rank 50: ${pred_rank50:,.0f}")
        return float(a), float(b)
    except Exception as e:
        print(f"  Curve fit failed: {e}")
        return None


def extrapolate_nil_values(on3_players: list[dict], a: float, b: float) -> list[dict]:
    """Fill in nil_value for unlabeled players using the fitted curve."""
    result = []
    for p in on3_players:
        p = dict(p)
        if not p.get("nil_value") and p.get("rank"):
            p["nil_value"] = float(power_law(np.array([float(p["rank"])]), a, b)[0])
            p["nil_source"] = "on3_extrapolated"
        else:
            p["nil_source"] = "on3_actual"
        result.append(p)
    return result


# ---------------------------------------------------------------------------
# Step 2 — Name matching helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())

SCHOOL_ALIASES = {
    "ohio st": "ohio state",
    "michigan st": "michigan state",
    "penn st": "penn state",
    "miss st": "mississippi state",
    "mississippi": "ole miss",
    "fsu": "florida state",
    "usc": "usc",
    "ucla": "ucla",
    "lsu": "lsu",
    "tcu": "tcu",
    "byu": "byu",
    "ucf": "ucf",
}

def norm_school(s: str) -> str:
    s = _norm(s)
    return SCHOOL_ALIASES.get(s, s)


# ---------------------------------------------------------------------------
# Step 3 — Feature engineering
# ---------------------------------------------------------------------------

def safe_log(x, min_val=1.0) -> float:
    return math.log10(max(float(x or 0), min_val))


def build_features(player, stats, social) -> dict:
    """Build a flat feature dict for one player."""
    # Social features
    ig  = float(social.instagram_followers or 0) if social else 0.0
    tw  = float(social.twitter_followers  or 0) if social else 0.0
    tik = 0.0  # TikTok not in DB yet
    total_followers = ig + tw + tik

    eng_rate = float(social.engagement_rate or 0) if social else 0.0
    verified = int(bool(social.verified_instagram)) if social else 0

    # Performance features
    total_yards   = float(stats.total_yards or 0)    if stats else 0.0
    touchdowns    = float(stats.touchdowns or 0)     if stats else 0.0
    ypg           = float(stats.yards_per_game or 0) if stats else 0.0
    efficiency    = float(stats.efficiency_metric or 0) if stats else 0.0
    team_wins     = float(stats.team_wins or 0)      if stats else 0.0
    has_stats     = int(stats is not None)

    # School / position / conference
    school_score  = calculate_school_score(player)
    pos_mult      = get_position_multiplier(player.position)
    conf_mult     = get_conference_multiplier(player.conference)

    # Class year (1=FR, 2=SO, 3=JR, 4=SR); None → 0
    class_year    = float(player.class_year or 0) if hasattr(player, "class_year") else 0.0

    # School tier one-hot
    school = (player.school or "").strip()
    tier1  = int(school in TIER1_SCHOOLS)
    tier2  = int(school in TIER2_SCHOOLS)

    # Conference one-hot
    conf = (player.conference or "").strip()
    conf_sec    = int(conf == "SEC")
    conf_b10    = int(conf == "Big Ten")
    conf_acc    = int(conf == "ACC")
    conf_b12    = int(conf == "Big 12")

    # Position one-hot (key positions)
    pos = (player.position or "").upper().strip()
    pos_qb = int(pos == "QB")
    pos_wr = int(pos == "WR")
    pos_rb = int(pos == "RB")
    pos_te = int(pos == "TE")
    pos_db = int(pos in ("DB", "CB", "S", "SS", "FS"))
    pos_dl = int(pos in ("DL", "DE", "DT"))
    pos_lb = int(pos == "LB")

    return {
        # Log-scaled social (most important for NIL)
        "log_ig_followers":    safe_log(ig),
        "log_tw_followers":    safe_log(tw),
        "log_total_followers": safe_log(total_followers),
        "engagement_rate":     eng_rate,
        "verified_instagram":  verified,
        # Performance
        "total_yards":         total_yards,
        "touchdowns":          touchdowns,
        "yards_per_game":      ypg,
        "efficiency_metric":   efficiency,
        "team_wins":           team_wins,
        "has_stats":           has_stats,
        # School / prestige
        "school_score":        school_score,
        "tier1_school":        tier1,
        "tier2_school":        tier2,
        # Position
        "pos_mult":            pos_mult,
        "pos_qb":              pos_qb,
        "pos_wr":              pos_wr,
        "pos_rb":              pos_rb,
        "pos_te":              pos_te,
        "pos_db":              pos_db,
        "pos_dl":              pos_dl,
        "pos_lb":              pos_lb,
        # Conference
        "conf_mult":           conf_mult,
        "conf_sec":            conf_sec,
        "conf_b10":            conf_b10,
        "conf_acc":            conf_acc,
        "conf_b12":            conf_b12,
        # Class year
        "class_year":          class_year,
        "is_underclassman":    int(class_year in (1.0, 2.0)),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build NIL ML training dataset")
    parser.add_argument("--test-size", type=float, default=0.2, help="Fraction held out for testing")
    parser.add_argument("--min-nil", type=float, default=500, help="Minimum NIL value to include as label")
    parser.add_argument("--season", type=int, default=2023)
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    # --- Load On3 scrape data ---
    on3_raw = []
    if os.path.exists(ON3_PATH):
        with open(ON3_PATH) as f:
            on3_raw = json.load(f)
        # Filter out noise: missing name or HS keywords — keep rows with missing nil_value
        # so the rank-based extrapolation step can fill them in
        on3_raw = [
            p for p in on3_raw
            if p.get("name")
            and not any(kw in (p.get("name") or "").lower() for kw in HS_KEYWORDS)
        ]
        print(f"Loaded {len(on3_raw)} clean On3 players from scrape")
    else:
        print("No on3_rankings.json found — using supplement only")

    # --- Load supplement (manually curated known NIL values) ---
    suppl = []
    if os.path.exists(SUPPL_PATH):
        with open(SUPPL_PATH) as f:
            suppl = json.load(f)
        print(f"Loaded {len(suppl)} players from nil_supplement.json")

    # Merge: supplement takes priority over scrape.
    # Key = (norm_name, norm_school) when school is present, else (norm_name, "")
    # to avoid dropping distinct players who share a name at different schools.
    def _dedup_key(p: dict) -> tuple:
        n = _norm(p.get("name", ""))
        s = _norm(p.get("school", "") or "")
        return (n, s) if s else (n, "")

    seen_keys: dict[tuple, dict] = {_dedup_key(p): p for p in suppl}
    for p in on3_raw:
        k = _dedup_key(p)
        if k not in seen_keys:
            seen_keys[k] = p
    on3_raw = list(seen_keys.values())
    print(f"Combined unique labeled players: {len(on3_raw)}")

    labeled = [p for p in on3_raw if p.get("nil_value")]
    print(f"  With NIL value: {len(labeled)}")

    # --- Fit curve ---
    print("\nFitting rank → NIL value curve...")
    curve = fit_rank_curve(on3_raw)
    if curve:
        a, b = curve
        on3_extended = extrapolate_nil_values(on3_raw, a, b)
    else:
        # No curve — use only labeled data
        on3_extended = [dict(p, nil_source="on3_actual") for p in on3_raw if p.get("nil_value")]
        print("  Using only labeled data (no extrapolation)")

    on3_extended = [p for p in on3_extended if p.get("nil_value", 0) >= args.min_nil]
    print(f"  Total labeled+extrapolated: {len(on3_extended)}")

    # Save labels CSV
    pd.DataFrame(on3_extended).to_csv(LABELS_PATH, index=False)
    print(f"  Saved labels to {LABELS_PATH}")

    # --- Load DB players + features ---
    print(f"\nLoading DB data for season {args.season}...")
    players  = get_all_players()
    stats_l  = get_all_performance_stats_by_season(args.season)
    social_l = get_all_social_media()
    print(f"  Players: {len(players)}, Stats: {len(stats_l)}, Social: {len(social_l)}")

    stats_by_pid  = {s.player_id: s for s in stats_l}
    social_by_pid = {s.player_id: s for s in social_l}

    # Filter: season=2023, not NFL drafted, has social or stats
    players = [
        p for p in players
        if p.season == args.season
        and not getattr(p, "nfl_drafted_2024", False)
        and (p.id in stats_by_pid or p.id in social_by_pid)
    ]
    print(f"  After filters (season + not drafted + has data): {len(players)}")

    # Build name→player lookup for On3 matching
    player_by_norm: dict[str, list] = {}
    player_by_norm_school: dict[tuple, object] = {}
    for p in players:
        nn = _norm(p.name)
        player_by_norm.setdefault(nn, []).append(p)
        player_by_norm_school[(_norm(p.name), norm_school(p.school or ""))] = p

    # --- Match On3 players to DB and build labeled rows ---
    print("\nMatching On3 players to DB...")
    rows = []
    on3_matched = on3_unmatched = 0

    for on3p in on3_extended:
        on3_name   = _norm(on3p.get("name") or "")
        on3_school = norm_school(on3p.get("school") or "")

        player = (
            player_by_norm_school.get((on3_name, on3_school))
            or (player_by_norm.get(on3_name, [None] * 2)[0] if len(player_by_norm.get(on3_name, [])) == 1 else None)
        )

        if player is None:
            on3_unmatched += 1
            continue

        on3_matched += 1
        stats  = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)

        feats = build_features(player, stats, social)
        feats["player_id"]  = player.id
        feats["name"]       = player.name
        feats["school"]     = player.school
        feats["nil_value"]  = on3p["nil_value"]
        feats["nil_source"] = on3p.get("nil_source", "on3_actual")
        feats["on3_rank"]   = on3p.get("rank")
        rows.append(feats)

    print(f"  On3 matched to DB: {on3_matched} | unmatched: {on3_unmatched}")

    # --- Also build feature rows for ALL DB players (for inference later) ---
    print("\nBuilding full feature matrix for all DB players...")
    all_rows = []
    for player in players:
        stats  = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)
        feats  = build_features(player, stats, social)
        feats["player_id"] = player.id
        feats["name"]      = player.name
        feats["school"]    = player.school
        feats["nil_value"] = None
        feats["nil_source"] = None
        feats["on3_rank"]  = None
        all_rows.append(feats)

    all_df = pd.DataFrame(all_rows)
    all_df.to_csv(os.path.join(DATA_DIR, "all_players_features.csv"), index=False)
    print(f"  Saved all_players_features.csv ({len(all_df)} rows)")

    # --- Train / test split on labeled rows ---
    if len(rows) < 10:
        print(f"\nWARNING: Only {len(rows)} labeled rows matched to DB.")
        print("  Train/test split skipped. Run pull_on3_nil.py to get more On3 data.")
        return

    df = pd.DataFrame(rows)
    print(f"\nLabeled dataset: {len(df)} rows")
    print(f"  NIL value range: ${df['nil_value'].min():,.0f} – ${df['nil_value'].max():,.0f}")
    print(f"  Sources: {df['nil_source'].value_counts().to_dict()}")

    train_df, test_df = train_test_split(df, test_size=args.test_size, random_state=42)
    train_df.to_csv(TRAIN_PATH, index=False)
    test_df.to_csv(TEST_PATH, index=False)
    print(f"\nSaved train.csv ({len(train_df)} rows) and test.csv ({len(test_df)} rows)")

    # Summary
    feature_cols = [c for c in df.columns if c not in ("player_id", "name", "school", "nil_value", "nil_source", "on3_rank")]
    print(f"\nFeature columns ({len(feature_cols)}): {feature_cols}")
    print("\nSample training rows:")
    print(train_df[["name", "school", "nil_value", "nil_source", "log_total_followers", "pos_qb", "conf_sec"]].head(10).to_string())


if __name__ == "__main__":
    main()
