"""
Calibrate the NIL formula to real dollar amounts using labeled data.

Strategy:
  1. Compute formula composite scores (0-100) for all labeled players
  2. Fit log10(nil_value) ~ formula_score using robust regression
  3. Apply the calibration to ALL DB players
  4. This preserves the formula's ranking while using real dollar scale

Output: data/nil_predictions_calibrated.csv + data/calibration.pkl

Usage:
    python src/valuation/calibrate_model.py --season 2024
    python src/valuation/calibrate_model.py --season 2023
"""
import os
import sys
import re
import json
import pickle
import argparse
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_percentage_error

from db.crud import get_all_players, get_all_performance_stats_by_season, get_all_social_media
from valuation.model import estimate_nil_value

DATA_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
SUPPL_PATH  = os.path.join(DATA_DIR, "nil_supplement.json")
ON3_PATH    = os.path.join(DATA_DIR, "on3_rankings.json")
WEB_PATH    = os.path.join(DATA_DIR, "nil_websearch.json")
RANK_PATH   = os.path.join(DATA_DIR, "on3_rank_labels.json")
CAL_PATH    = os.path.join(DATA_DIR, "calibration.pkl")

HS_KEYWORDS = {"high", "school", "prep", "academy", "little elm", "archbishop",
               "forest hills", "isidore", "west linn", "lake dallas",
               "martin luther king", "south florence", "st joseph", "chaminade"}

# Curated labels have no floor — they cover the full $700K–$6.8M range.
# Rank-based soft labels extend coverage down to ~$50K.
MIN_NIL_LABEL = 50_000


def _social_tier(social_score: float) -> float:
    """Bucketed social tier (0-100) matching real NIL market thresholds.

    The log-scale social_score compresses 100K vs 200K followers to nearly
    identical values (~72 vs ~78), but in the market 200K is worth ~2×.
    Buckets capture the non-linear jump at each follower threshold.
    Buckets map approximately to follower counts:
      <10K→5, 10K-50K→20, 50K-100K→40, 100K-200K→60, 200K-500K→80, 500K+→100
    Since social_score is already log-scaled from followers, we reverse-map:
      social_score uses cap of 3M, log10(3M)≈6.48. Approx score for 10K=log10(10K)/log10(3M)≈57%.
    We just bucket the social_score directly at empirical thresholds.
    """
    if social_score >= 90:   return 100.0   # ~500K+ followers
    if social_score >= 80:   return 80.0    # ~200K-500K
    if social_score >= 70:   return 60.0    # ~100K-200K
    if social_score >= 55:   return 40.0    # ~50K-100K
    if social_score >= 35:   return 20.0    # ~10K-50K
    return 5.0                               # <10K


def _feature_vector(res: dict, position: str = "", stat_pct: float = 0.0,
                    role_score: float = 0.0) -> list[float]:
    """Extract 13 normalised features from estimate_nil_value() result dict.

    Base 8 + has_stats + is_QB + social_tier + stat_pct + role_score:
      is_QB:      binary 100/0 — QBs earn 2-3× non-QBs for same features.
      social_tier: bucketed social score capturing non-linear follower jumps.
      stat_pct:   percentile of player's total_yards within their position group
                  (0-100). Distinguishes backup RBs from starters at same school.
      role_score: usage/starter signal (0-100) based on raw attempt/yard counts.
                  A backup QB with 5 pass attempts scores ~2; a starter with 300
                  scores 100. Provides a direct, non-percentile starter signal
                  that the regression can use independently of stat_pct.
    """
    perf_score       = res["perf_score"]           # 0-100
    social_score     = res["social_score"]         # 0-100
    school_score     = res["school_score"]         # 0-100
    pos_score        = (res["position_mult"]   - 0.7) / (1.5 - 0.7) * 100.0
    conf_score       = (res["conference_mult"] - 0.8) / (1.3 - 0.8) * 100.0
    class_score      = res["class_score"]          # 0-100
    recruit_score    = res.get("recruit_score", 20.0)
    collective_score = res.get("collective_score", 10.0)  # 0-100, G5 default=10
    has_stats        = 100.0 if perf_score > 0 else 0.0   # starter signal
    is_qb            = 100.0 if (position or "").upper() == "QB" else 0.0
    soc_tier         = _social_tier(social_score)
    return [perf_score, social_score, school_score, pos_score, conf_score,
            class_score, recruit_score, collective_score, has_stats, is_qb,
            soc_tier, stat_pct, role_score]


# Skill positions that accumulate countable yards/stats
_SKILL_POSITIONS = {"QB", "RB", "WR", "TE", "FB", "SLOT"}


def _build_pos_stat_arrays(stats_list, players_by_pid: dict) -> dict:
    """Build sorted total_yards arrays by position for percentile lookup."""
    pos_yards: dict[str, list] = {}
    for s in stats_list:
        p = players_by_pid.get(s.player_id)
        if p:
            pos = (p.position or "").upper()
            if pos in _SKILL_POSITIONS:
                yards = getattr(s, "total_yards", 0) or 0
                if yards > 0:
                    pos_yards.setdefault(pos, []).append(yards)
    return {pos: np.sort(arr) for pos, arr in pos_yards.items()}


def _stat_percentile(player, stats, pos_arrays: dict) -> float:
    """Return 0-100 percentile of player's total_yards among their position peers."""
    pos = (getattr(player, "position", None) or "").upper()
    if pos not in _SKILL_POSITIONS or stats is None:
        return 0.0
    yards = getattr(stats, "total_yards", 0) or 0
    if yards == 0:
        return 0.0
    arr = pos_arrays.get(pos)
    if arr is None or len(arr) == 0:
        return 50.0
    return round(float(np.searchsorted(arr, yards, side="right")) / len(arr) * 100, 1)


def _role_score(stats, position: str) -> float:
    """Usage/role score (0-100): featured starter → high, backup/no stats → low.

    Distinguishes a starting QB (300 pass attempts) from a backup QB (10 attempts)
    at the same school. Position-aware:
      QB:       pass attempts 0-300 → 0-100
      RB/FB:    rush attempts 0-150 → 0-100
      WR/TE:    total_yards   0-800 → 0-100
      Other:    always 0 (OL/DL have no direct usage proxy)
    """
    if stats is None:
        return 0.0
    pos = (position or "").upper()
    attempts    = getattr(stats, "attempts",    0) or 0
    total_yards = getattr(stats, "total_yards", 0) or 0

    if pos == "QB":
        return min(100.0, attempts / 3.0)
    if pos in ("RB", "FB"):
        return min(100.0, attempts / 1.5)
    if pos in ("WR", "TE", "SLOT"):
        return min(100.0, total_yards / 8.0) if total_yards > 0 else 0.0
    return 0.0


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())


def load_labels(season: int = 2024) -> list[dict]:
    """Load labeled NIL players for calibration.

    Two tiers of labels:
    1. Curated (WEB_PATH): 48 hand-verified On3 valuations — high confidence,
       cover the $700K–$6.8M range. Used as primary training signal.
    2. Rank-based soft labels (RANK_PATH): 3,796 players with On3-rank-derived
       estimates via power-law curve. Lower confidence but cover the full
       $50K–$1.5M range the curated set misses entirely.
    """
    labels = []
    seen: set[tuple] = set()

    # Tier 1: curated labels (highest confidence)
    if os.path.exists(WEB_PATH):
        for p in json.load(open(WEB_PATH)):
            n = norm(p.get("name", ""))
            s = norm(p.get("school", "") or "")
            key = (n, s) if s else (n, "")
            if key not in seen and p.get("nil_value") and p["nil_value"] >= MIN_NIL_LABEL \
                    and not any(kw in n for kw in HS_KEYWORDS):
                seen.add(key)
                labels.append(p)

    # Tier 2: rank-tier band anchors.
    # Conservative anchor values prevent power-law over-estimation for ranks 300+.
    # Kept deliberately small (8 per band) so the curated labels remain the primary
    # training signal. Too many noisy rank anchors corrupt the regression.
    # Per-band weights decrease with rank uncertainty.
    RANK_BANDS = [
        # (rank_lo, rank_hi, anchor_value, per_band_cap, band_weight)
        (26,   100,   1_500_000, 8,  1.0),    # P4 starters, national visibility
        (101,  300,     800_000, 8,  0.8),    # solid starters, regional recognition
        (301,  1000,    400_000, 8,  0.5),    # roster contributors
        (1001, 99999,   180_000, 8,  0.4),    # depth players, walk-ons
    ]
    if os.path.exists(RANK_PATH):
        rank_labels = json.load(open(RANK_PATH))
        # Sort by rank ascending (best first)
        rank_labels.sort(key=lambda x: x.get("rank") or 99999)

        import random as _random
        _random.seed(7)

        total_anchors = 0
        for (rlo, rhi, anchor_val, cap, band_w) in RANK_BANDS:
            band = [
                p for p in rank_labels
                if rlo <= (p.get("rank") or 99999) <= rhi
                and not any(kw in norm(p.get("name", "")) for kw in HS_KEYWORDS)
            ]
            sampled = _random.sample(band, min(cap, len(band)))
            for p in sampled:
                n = norm(p.get("name", ""))
                s = norm(p.get("school", "") or "")
                key = (n, s) if s else (n, "")
                if key in seen:
                    continue
                seen.add(key)
                labels.append({
                    "name":      p["name"],
                    "school":    p.get("school", ""),
                    "position":  p.get("position", ""),
                    "nil_value": anchor_val,
                    "source":    "rank_anchor",
                    "_weight":   band_w,   # per-band weight (higher = more confident)
                })
                total_anchors += 1
        print(f"  Rank-tier anchor labels added: {total_anchors}")

    return labels


def main():
    parser = argparse.ArgumentParser(description="Calibrate NIL formula to real dollar amounts")
    parser.add_argument("--season", type=int, default=2024)
    args = parser.parse_args()

    print("Loading labels...")
    labels = load_labels(season=args.season)
    print(f"  {len(labels)} labeled players")

    # Load primary season for all-player predictions
    print(f"\nLoading DB for season {args.season}...")
    all_players   = get_all_players()
    players       = [p for p in all_players if p.season == args.season]
    stats_l       = get_all_performance_stats_by_season(args.season)
    social_l      = get_all_social_media()
    stats_by_pid  = {s.player_id: s for s in stats_l}
    social_by_pid = {s.player_id: s for s in social_l}
    print(f"  {len(players)} players, {len(stats_l)} stats, {len(social_l)} social rows")

    # Build position-level stat percentile arrays for starter vs backup discrimination
    pos_arrays = _build_pos_stat_arrays(stats_l, {p.id: p for p in players})

    # Also load adjacent season for cross-season training
    # (labeled players who graduated/went pro won't be in the primary season)
    other_season = 2024 if args.season == 2025 else 2025
    print(f"\nLoading DB for season {other_season} (cross-season training)...")
    players_other   = [p for p in all_players if p.season == other_season]
    stats_other_l   = get_all_performance_stats_by_season(other_season)
    stats_by_pid_other  = {s.player_id: s for s in stats_other_l}
    # social_by_pid is shared (player_id is unique across seasons)
    print(f"  {len(players_other)} players, {len(stats_other_l)} stats")

    # Build lookups for BOTH seasons
    def _build_lookups(player_list):
        by_ns   = {(norm(p.name), norm(p.school or "")): p for p in player_list}
        by_name = {}
        for p in player_list:
            by_name.setdefault(norm(p.name), []).append(p)
        return by_ns, by_name

    p_by_ns,       p_by_name       = _build_lookups(players)
    p_by_ns_other, p_by_name_other = _build_lookups(players_other)

    # Build name→social lookup so 2025 players missing social can use their 2024 row
    social_by_name: dict[str, object] = {}
    all_players_by_pid = {p.id: p for p in all_players}
    for s in social_l:
        if (s.total_followers or 0) > 0:
            p = all_players_by_pid.get(s.player_id)
            if p:
                social_by_name[norm(p.name)] = s

    # --- Match labels to DB (primary season first, fall back to other season) ---
    # Priority: school-exact match > name-only fallback.
    # Transfer players (label school ≠ old school) should use the label's school season
    # so features reflect the program context for which the NIL value was earned.
    print("\nMatching labels and extracting features (cross-season)...")
    matched_features, matched_nil, matched_meta = [], [], []

    for lbl in labels:
        nn = norm(lbl.get("name", ""))
        ns = norm(lbl.get("school", ""))

        player     = None
        used_season = args.season
        stats_map   = stats_by_pid

        # 1. Try exact (name, school) in primary season
        player = p_by_ns.get((nn, ns))

        # 2. Try exact (name, school) in other season (preferred over name-only mismatch)
        if not player:
            p_other = p_by_ns_other.get((nn, ns))
            if p_other:
                player      = p_other
                used_season = other_season
                stats_map   = stats_by_pid_other

        # 3. Name-only fallback in primary season (only if unique)
        if not player:
            cands = p_by_name.get(nn, [])
            player = cands[0] if len(cands) == 1 else None

        # 4. Name-only fallback in other season (only if unique)
        if not player:
            cands = p_by_name_other.get(nn, [])
            if len(cands) == 1:
                player      = cands[0]
                used_season = other_season
                stats_map   = stats_by_pid_other

        if not player:
            continue

        stats  = stats_map.get(player.id)
        social = social_by_pid.get(player.id)
        # If no social for this player_id, fall back to any season's data by name
        if social is None or (social.total_followers or 0) == 0:
            social = social_by_name.get(norm(player.name))
        res    = estimate_nil_value(player, stats, social, base_value=100.0)

        sp   = _stat_percentile(player, stats, pos_arrays)
        rs   = _role_score(stats, player.position or "")
        fvec = _feature_vector(res, position=player.position or "", stat_pct=sp, role_score=rs)
        matched_features.append(fvec)
        matched_nil.append(lbl["nil_value"])
        src = lbl.get("source", "")
        matched_meta.append({
            "player_id":    player.id,
            "name":         player.name,
            "school":       player.school,
            "position":     player.position,
            "season_used":  used_season,
            "features":     fvec,
            "actual_nil":   lbl["nil_value"],
            "source":       src,
            # Curated (web_2025) = 5×
            # AI-verified (ai_search_2025) = 1× — reduced from 2× to prevent low-tier
            #   labels from diluting elite accuracy. Curated labels (235 total weight)
            #   need to dominate; low-tier caps handled via post-processing.
            # rank-tier anchors = 0.2–1.0 (per-band, stored in _weight)
            # DDG-scraped (web_search_2025) = 0 (not trusted yet)
            "weight":       5.0 if src == "web_2025" else (
                            1.0 if src == "ai_search_2025" else (
                            lbl.get("_weight", 1.0) if src == "rank_anchor" else 0.0)),
        })

    print(f"  Matched: {len(matched_meta)} players (including duplicates)")

    # Deduplicate by player_id — same player can appear from multiple label sources
    seen_pids: set = set()
    deduped = [(f, v, m) for f, v, m in zip(matched_features, matched_nil, matched_meta)
               if m["player_id"] not in seen_pids and not seen_pids.add(m["player_id"])]
    matched_features = [d[0] for d in deduped]
    matched_nil      = [d[1] for d in deduped]
    matched_meta     = [d[2] for d in deduped]
    sample_weights   = np.array([m["weight"] for m in matched_meta])
    print(f"  After dedup: {len(matched_meta)} unique players")

    if len(matched_meta) < 5:
        print("ERROR: Need at least 5 matched players.")
        sys.exit(1)

    X_raw = np.array(matched_features)   # shape: (n_labeled, 7)
    y = np.array([math.log10(v) for v in matched_nil])

    # Print feature summary to diagnose zero-collapse
    feature_names = ["perf", "social", "school", "position", "conference", "class_year", "recruit", "collective", "has_stats", "is_QB", "social_tier", "stat_pct", "role_score"]
    print(f"\n  Feature means (raw, 0-100 scale):")
    for i, fname in enumerate(feature_names):
        col = X_raw[:, i]
        n_zero = np.sum(col == 0)
        print(f"    {fname:<15}: mean={col.mean():.1f}  std={col.std():.1f}  zeros={n_zero}/{len(col)}")

    # --- Fit regression model in log space ---
    # Try multiple model variants; pick best by within-20% accuracy on training set.
    # Reject any model that predicts >$20M for any training player (sanity check).
    from sklearn.linear_model import Ridge, HuberRegressor

    ya = np.array(matched_nil)
    MAX_SANE_NIL = 20_000_000

    # Build all feature matrix variants up front
    # V1: base 8 features
    scaler_base = StandardScaler()
    X_base = scaler_base.fit_transform(X_raw)

    # V2: 8 base + perf^2/100 (amplifies starter vs backup signal)
    X_p2_raw = np.column_stack([X_raw, X_raw[:, 0] ** 2 / 100.0])
    scaler_p2 = StandardScaler()
    X_p2 = scaler_p2.fit_transform(X_p2_raw)

    # V3: 9 base + 4 interaction terms (original set)
    inter_pairs = [(2, 4), (1, 6), (7, 3), (0, 3)]  # school×conf, social×recruit, collective×pos, perf×pos
    inter_names_suffix = ["school×conf", "social×recruit", "collective×pos", "perf×pos"]
    X_inter_raw = np.column_stack(
        [X_raw] + [X_raw[:, i] * X_raw[:, j] / 100.0 for i, j in inter_pairs]
    )
    scaler_inter = StandardScaler()
    X_inter = scaler_inter.fit_transform(X_inter_raw)

    # V4: 9 base + 4 alternative interactions (perf×collective replaces collective×pos)
    # perf×collective: high-NIL elite-school players must have stats (penalises backups at Texas/Ohio State)
    # recruit×class_year: 5-star freshmen have higher name value than 5-star seniors
    inter_pairs2 = [(0, 7), (1, 6), (2, 4), (6, 5)]  # perf×collective, social×recruit, school×conf, recruit×class_year
    inter_names_suffix2 = ["perf×collective", "social×recruit", "school×conf", "recruit×class_year"]
    X_inter2_raw = np.column_stack(
        [X_raw] + [X_raw[:, i] * X_raw[:, j] / 100.0 for i, j in inter_pairs2]
    )
    scaler_inter2 = StandardScaler()
    X_inter2 = scaler_inter2.fit_transform(X_inter2_raw)

    # V5: inter2 + is_QB×social interaction
    # is_QB×social (indices 9,1): QB premium scales with social following.
    # Elite QBs (Arch Manning, Shedeur) keep full QB bonus; backup QBs at top schools
    # (Marcel Reed, Beau Pribula) get a lower QB premium proportional to their social presence.
    inter_pairs3 = [(0, 7), (1, 6), (2, 4), (6, 5), (9, 1)]  # inter2 + is_QB×social
    inter_names_suffix3 = ["perf×collective", "social×recruit", "school×conf", "recruit×class_year", "is_QB×social"]
    X_inter3_raw = np.column_stack(
        [X_raw] + [X_raw[:, i] * X_raw[:, j] / 100.0 for i, j in inter_pairs3]
    )
    scaler_inter3 = StandardScaler()
    X_inter3 = scaler_inter3.fit_transform(X_inter3_raw)

    # V6: inter3 + stat_pct×collective interaction
    # stat_pct×collective (indices 11,7): featured players at high-collective elite schools
    # earn premium; backups at the same schools don't. Directly targets the CJ Baxter problem:
    # backup RBs at Texas/Georgia have high collective but low stat_pct → low NIL.
    inter_pairs4 = [(0, 7), (1, 6), (2, 4), (6, 5), (9, 1), (11, 7), (12, 9)]  # inter3 + stat_pct×collective + role_score×is_QB
    inter_names_suffix4 = ["perf×collective", "social×recruit", "school×conf", "recruit×class_year", "is_QB×social", "stat_pct×collective", "role×is_QB"]
    X_inter4_raw = np.column_stack(
        [X_raw] + [X_raw[:, i] * X_raw[:, j] / 100.0 for i, j in inter_pairs4]
    )
    scaler_inter4 = StandardScaler()
    X_inter4 = scaler_inter4.fit_transform(X_inter4_raw)

    # Each variant stores: (X_fitted, feature_scaler, raw_matrix, build_fn, name_list)
    # build_fn converts raw 9-feature vector → extended vector for this variant
    variants = [
        (X_base,   scaler_base,   X_raw,        lambda v: list(v),
         feature_names, "base"),
        (X_p2,     scaler_p2,     X_p2_raw,     lambda v: list(v) + [v[0] ** 2 / 100.0],
         feature_names + ["perf²"], "perf²"),
        (X_inter,  scaler_inter,  X_inter_raw,  lambda v: list(v) + [v[i] * v[j] / 100.0 for i, j in inter_pairs],
         feature_names + inter_names_suffix, "inter"),
        (X_inter2, scaler_inter2, X_inter2_raw, lambda v: list(v) + [v[i] * v[j] / 100.0 for i, j in inter_pairs2],
         feature_names + inter_names_suffix2, "inter2"),
        (X_inter3, scaler_inter3, X_inter3_raw, lambda v: list(v) + [v[i] * v[j] / 100.0 for i, j in inter_pairs3],
         feature_names + inter_names_suffix3, "inter3"),
        (X_inter4, scaler_inter4, X_inter4_raw, lambda v: list(v) + [v[i] * v[j] / 100.0 for i, j in inter_pairs4],
         feature_names + inter_names_suffix4, "inter4"),
    ]

    best_w20, best_reg, best_label = -1, None, None
    best_build_fn  = variants[0][3]
    best_scaler_v  = scaler_base
    best_names     = feature_names
    best_tag       = "base"

    eps_values = [round(1.0 + e * 0.05, 2) for e in range(11)] + [1.55, 1.6, 1.7, 1.8, 2.0, 3.0]
    alpha_ridge = [0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0]
    alpha_inter = [1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]

    # inter3/inter4 have more interaction terms — use stronger regularization
    alpha_inter34 = [50.0, 100.0, 500.0, 1000.0, 2000.0]

    for (X_v, sc_v, _, build_fn, names_v, tag) in variants:
        alphas = alpha_inter34 if tag in ("inter3", "inter4") else (alpha_inter if tag in ("inter", "inter2") else alpha_ridge)
        # Ridge
        for alpha_try in alphas:
            r = Ridge(alpha=alpha_try, fit_intercept=True)
            r.fit(X_v, y, sample_weight=sample_weights)
            yp_raw = 10 ** r.predict(X_v)
            if np.any(yp_raw > MAX_SANE_NIL):
                continue
            yp = np.clip(yp_raw, 200_000, 8_000_000)
            # Score only on original curated labels (weight=5.0)
            mask = sample_weights >= 5.0
            w20 = np.mean(np.abs(yp[mask] - ya[mask]) / ya[mask] <= 0.20) if mask.any() else 0
            if w20 > best_w20:
                best_w20, best_reg, best_label = w20, r, f"Ridge-{tag}(alpha={alpha_try})"
                best_build_fn, best_scaler_v, best_names, best_tag = build_fn, sc_v, names_v, tag
        # Huber
        for eps in eps_values:
            try:
                h = HuberRegressor(epsilon=eps, max_iter=3000)
                h.fit(X_v, y, sample_weight=sample_weights)
                yp_raw = 10 ** h.predict(X_v)
                if np.any(yp_raw > MAX_SANE_NIL):
                    continue
                yp = np.clip(yp_raw, 200_000, 8_000_000)
                mask = sample_weights >= 5.0
                w20 = np.mean(np.abs(yp[mask] - ya[mask]) / ya[mask] <= 0.20) if mask.any() else 0
                if w20 > best_w20:
                    best_w20, best_reg, best_label = w20, h, f"Huber-{tag}(eps={eps})"
                    best_build_fn, best_scaler_v, best_names, best_tag = build_fn, sc_v, names_v, tag
            except Exception:
                pass

    reg = best_reg
    print(f"\n  Best model: {best_label}  (within-20% on curated: {best_w20*100:.1f}%)")

    print(f"\n  Learned feature weights (log10 space, standardised):")
    for fname, coef in zip(best_names, reg.coef_):
        print(f"    {fname:<16}: {coef:+.4f}")
    print(f"    {'intercept':<16}: {reg.intercept_:+.4f}")

    def _to_model_features(fvec_raw):
        """Transform raw 8-feature vector to the format expected by the winning model."""
        return best_scaler_v.transform([best_build_fn(np.array(fvec_raw))])[0]

    # Build X_fit from the winning variant's raw matrix (for in-sample accuracy)
    for (_, sc_v, X_v_raw, build_fn, names_v, _tag) in variants:
        if sc_v is best_scaler_v:
            X_fit = sc_v.transform(X_v_raw)
            break

    # --- In-sample accuracy ---
    y_pred_log = reg.predict(X_fit)
    y_actual   = np.array(matched_nil)
    y_pred     = np.clip(10 ** y_pred_log, 50_000, 8_000_000)
    mape = mean_absolute_percentage_error(y_actual, y_pred) * 100
    spear_r, spear_p = spearmanr(y_actual, y_pred)

    curated_mask = sample_weights >= 5.0   # original web_2025 labels only
    all_web_mask = sample_weights >= 1.0   # curated + ai_search + rank_anchors
    within_20_curated = (np.mean(np.abs(y_pred[curated_mask] - y_actual[curated_mask])
                                  / y_actual[curated_mask] <= 0.20) * 100
                         if curated_mask.any() else 0.0)
    within_20_all_web = (np.mean(np.abs(y_pred[all_web_mask] - y_actual[all_web_mask])
                                  / y_actual[all_web_mask] <= 0.20) * 100
                         if all_web_mask.any() else 0.0)
    print(f"\n  In-sample MAPE:             {mape:.1f}%")
    print(f"  Within-20% (curated only):  {within_20_curated:.1f}%  (target: ≥70%)")
    print(f"  Within-20% (all web):       {within_20_all_web:.1f}%  ({int(all_web_mask.sum())} labels)")
    print(f"  Spearman rank correlation:  {spear_r:.3f} (p={spear_p:.4f})")
    print(f"  Target: MAPE <30%, Within-20% ≥70%, Spearman >0.6")

    # Tier-stratified accuracy: diagnose where the model is weakest
    print(f"\n  Tier-stratified accuracy (all web labels, within-20%):")
    tier_defs = [
        ("elite  (>$2.5M)",   2_500_000, float("inf")),
        ("high   ($1-2.5M)",  1_000_000, 2_500_000),
        ("mid    ($500K-$1M)",  500_000,   1_000_000),
        ("low    (<$500K)",          0,     500_000),
    ]
    for tier_name, lo, hi in tier_defs:
        mask = (ya >= lo) & (ya < hi) & (sample_weights >= 1.0)
        if mask.sum() > 0:
            w20_t = np.mean(np.abs(y_pred[mask] - ya[mask]) / ya[mask] <= 0.20) * 100
            med_err = np.median(np.abs(y_pred[mask] - ya[mask]) / ya[mask]) * 100
            print(f"    {tier_name:<22}: {w20_t:5.1f}%  (n={mask.sum():2d}, median-err={med_err:.1f}%)")

    print(f"\n  Per-player calibrated predictions:")
    print(f"  {'Name':<25} {'Actual':>12} {'Predicted':>12} {'Error%':>8} {'✓':>3} Source")
    print(f"  {'-'*76}")
    for i, m in enumerate(matched_meta):
        err = abs(y_pred[i] - m["actual_nil"]) / m["actual_nil"] * 100
        ok = "✓" if err <= 20.0 else "✗"
        print(f"  {m['name']:<25} ${m['actual_nil']:>11,.0f} ${y_pred[i]:>11,.0f} "
              f"{err:>7.1f}%  {ok}  {m['source']}")

    # --- Apply calibration to ALL players ---
    print(f"\nApplying calibration to all {len(players)} players...")
    results = []
    for player in players:
        if getattr(player, "nfl_drafted_2024", False):
            continue
        stats  = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)
        if social is None or (social.total_followers or 0) == 0:
            social = social_by_name.get(norm(player.name))
        res    = estimate_nil_value(player, stats, social, base_value=100.0)

        sp        = _stat_percentile(player, stats, pos_arrays)
        rs        = _role_score(stats, player.position or "")
        fvec      = _feature_vector(res, position=player.position or "", stat_pct=sp, role_score=rs)
        # Formula composite score (0-100): perf 20%, social 20%, school 15%, pos 12%, conf 8%, class 5%, recruit 20%
        # ML-only features (collective, has_stats, is_QB, social_tier, stat_pct) get 0 weight in display score
        composite = sum(f * w for f, w in zip(fvec, [0.20, 0.20, 0.15, 0.12, 0.08, 0.05, 0.20, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
        fvec_s    = _to_model_features(np.array(fvec))
        log_nil   = reg.predict([fvec_s])[0]
        # Base clip: $50K floor, $8M ceiling
        nil_value = max(50_000, min(8_000_000, 10 ** log_nil))
        # Sanity caps: prevent ML from wildly extrapolating for low-composite players.
        # Formula composite < threshold means the player lacks the underlying attributes
        # to justify elite NIL deals. These caps don't affect curated-label players
        # (all curated labels have composite >= 50.5 in training).
        perf_val    = fvec[0]   # perf_score
        recruit_val = fvec[6]   # recruit_score
        soc_raw     = fvec[1]   # social_score (0-100)
        no_meaningful_stats = perf_val < 5
        social_star = soc_raw >= 77  # ≈ 80K+ confirmed followers
        pos = (player.position or "").upper()
        if composite < 42:
            nil_value = min(nil_value, 1_500_000)
        elif composite < 55:
            nil_value = min(nil_value, 3_000_000)
        # Extra cap for no-stats players (walk-ons/non-contributors) without top recruit status
        if perf_val == 0 and recruit_val < 60:
            nil_value = min(nil_value, 2_000_000)
        # Position-group ceilings (Phase 2): non-QB positions have lower NIL ceilings.
        # Only the rarest exceptions (Jeremiah Smith-tier) exceed these.
        if pos in ("WR", "TE"):
            nil_value = min(nil_value, 4_000_000)   # elite WRs (Jeremiah Smith) can reach $4M+
        elif pos in ("RB",):
            nil_value = min(nil_value, 2_500_000)
        elif pos in ("OT", "OG", "OL", "C"):
            nil_value = min(nil_value, 2_000_000)
        elif pos in ("DE", "DL", "DT", "NT", "EDGE"):
            nil_value = min(nil_value, 2_500_000)   # elite pass rushers can earn more
        elif pos in ("LB", "ILB", "OLB"):
            nil_value = min(nil_value, 2_000_000)
        elif pos in ("CB", "S", "DB", "FS", "SS"):
            nil_value = min(nil_value, 1_500_000)
        elif pos in ("K", "P", "PK", "LS", "ST"):  # specialists rarely command big NIL
            nil_value = min(nil_value, 150_000)

        # Stat-percentile graduated ceilings for non-QB positions.
        # Social stars get higher tier caps (brand boosts their value) but are NOT fully exempt.
        # sp == 0 (no stats record) is handled by the no_meaningful_stats caps below.
        if sp > 0 and pos in ("RB", "FB"):
            if social_star:
                if sp <= 25:   nil_value = min(nil_value,   600_000)
                elif sp <= 55: nil_value = min(nil_value,   900_000)
                elif sp <= 75: nil_value = min(nil_value, 1_200_000)
                elif sp <= 89: nil_value = min(nil_value, 1_500_000)
                # sp >= 90: elite social + elite stats — full RB ceiling ($2.5M)
            else:
                if sp <= 25:   nil_value = min(nil_value,   400_000)
                elif sp <= 55: nil_value = min(nil_value,   600_000)
                elif sp <= 75: nil_value = min(nil_value,   800_000)
                elif sp <= 89: nil_value = min(nil_value, 1_100_000)
                # sp >= 90: elite — full RB ceiling ($2.5M)
        elif sp > 0 and pos in ("WR", "TE", "SLOT"):
            if social_star:
                if sp <= 25:   nil_value = min(nil_value,   700_000)
                elif sp <= 55: nil_value = min(nil_value, 1_100_000)
                elif sp <= 75: nil_value = min(nil_value, 1_500_000)
                elif sp <= 89: nil_value = min(nil_value, 2_000_000)
                # sp >= 90: elite — full WR ceiling ($4M)
            else:
                if sp <= 25:   nil_value = min(nil_value,   450_000)
                elif sp <= 55: nil_value = min(nil_value,   700_000)
                elif sp <= 75: nil_value = min(nil_value, 1_000_000)
                elif sp <= 89: nil_value = min(nil_value, 1_400_000)
                # sp >= 90: elite — full WR ceiling ($4M)
        # Non-skill positions: brand value is limited even for social stars
        elif sp > 0 and pos in ("OT", "OG", "OL", "C"):
            nil_value = min(nil_value, 700_000 if social_star else 500_000)
        elif sp > 0 and pos in ("DE", "DL", "DT", "NT", "EDGE"):
            nil_value = min(nil_value, 900_000 if social_star else 600_000)
        elif sp > 0 and pos in ("LB", "ILB", "OLB"):
            nil_value = min(nil_value, 900_000 if social_star else 600_000)
        elif sp > 0 and pos in ("CB", "S", "DB", "FS", "SS"):
            nil_value = min(nil_value, 800_000 if social_star else 500_000)

        # Social + starter floors: players with no market presence can't command real deals.
        # Follower-count calibration (soc_raw → approximate real followers):
        #   soc_raw 35 ≈ 200 followers   — essentially invisible
        #   soc_raw 55 ≈ 2,500 followers — tiny local following
        #   soc_raw 70 ≈ 22,000 followers — small but real presence
        #   soc_raw 80 ≈ 97,000 followers — meaningful brand (~100K)
        # NIL market reality: <10K followers + no meaningful stats ≈ no real market.
        # (soc_raw, no_meaningful_stats, social_star already defined above)
        if no_meaningful_stats and soc_raw == 0:
            # Elite recruits without social still have real market value from their football brand
            if recruit_val >= 85:
                nil_value = min(nil_value, 700_000)   # 5-star, no stats yet, no social
            elif recruit_val >= 60:
                nil_value = min(nil_value, 200_000)   # 4-star, no stats, no social
            else:
                nil_value = min(nil_value, 80_000)    # walk-on/unrated, invisible
        elif no_meaningful_stats and soc_raw < 55:
            if recruit_val >= 85:
                nil_value = min(nil_value, 700_000)   # elite recruit + tiny following
            else:
                nil_value = min(nil_value, 100_000)   # <2,500 followers + no production
        elif no_meaningful_stats and soc_raw < 70:
            nil_value = min(nil_value, 200_000)       # <22K followers, minimal market
        elif no_meaningful_stats and soc_raw < 77:
            nil_value = min(nil_value, 400_000)       # <80K followers, some market
        # Social stars with NO football profile (0 perf + no elite recruit):
        # big social following alone doesn't justify $1.5-2M without any production or prestige.
        elif social_star and no_meaningful_stats and recruit_val < 60:
            nil_value = min(nil_value, 800_000)       # social-only, no football value
        elif social_star and no_meaningful_stats and recruit_val < 85:
            nil_value = min(nil_value, 1_200_000)     # social + elite recruit, no stats yet
        # Zero social = essentially no NIL market regardless of stats below starter level
        # Exempt elite recruits — their football brand compensates for missing social data
        if soc_raw == 0 and perf_val < 30 and recruit_val < 85:
            nil_value = min(nil_value, 150_000)
        # Confirmed low-follower cap: when we KNOW a player has a tiny following, they lack
        # the brand market for significant NIL regardless of stats.
        # soc_raw == 0 means missing data (may have real followers), so we only cap when
        # soc_raw is confirmed low (> 0 but below threshold).
        #   soc_raw < 58  ≈ confirmed < 5K followers  → very limited brand market
        #   soc_raw < 62  ≈ confirmed < 10K followers → small but real local following
        if 0 < soc_raw < 58:
            nil_value = min(nil_value, 200_000)
        elif 0 < soc_raw < 62:
            nil_value = min(nil_value, 250_000)
        # Non-QB skill positions with minimal/no stats: social alone doesn't make NIL.
        # Exception: social stars (80K+ followers) can command brand deals without production.
        if pos in ("RB", "FB") and no_meaningful_stats and not social_star:
            nil_value = min(nil_value, 400_000)
        elif pos in ("WR", "TE", "SLOT") and no_meaningful_stats and not social_star:
            nil_value = min(nil_value, 400_000)
        # Non-skill positions with no stats: NIL is driven mainly by school + social,
        # but fans don't buy jerseys for OL/DL — hard cap even for social stars.
        #   social_star exempt: skill positions only (WR/RB/TE can model brand deals)
        #   OL/DL/LB: cap applies even with big following — production still required
        if pos in ("OT", "OG", "OL", "C") and no_meaningful_stats:
            nil_value = min(nil_value, 500_000)    # social star OL can still get brand deals up to ~$500K
        elif pos in ("DE", "DL", "DT", "NT", "EDGE") and no_meaningful_stats:
            nil_value = min(nil_value, 600_000)
        elif pos in ("LB", "ILB", "OLB") and no_meaningful_stats:
            nil_value = min(nil_value, 600_000)
        elif pos in ("CB", "S", "DB", "FS", "SS") and no_meaningful_stats and not social_star:
            nil_value = min(nil_value, 200_000)
        # QB-specific caps: backup/minimal-starter QBs carry far less NIL than starters.
        # Prevents walk-on/3rd-string QBs from hitting the $2M+ composite cap.
        if pos == "QB" and soc_raw == 0:
            # No social presence at all → tiny market regardless of school/position
            nil_value = min(nil_value, 200_000)
        elif pos == "QB" and perf_val == 0 and soc_raw < 50:
            nil_value = min(nil_value, 500_000)
        # No-production QB cap: even high-social QBs need real college reps to
        # justify $1.5M+. Exception: Arch Manning-level players are in curated labels
        # so the regression handles them — this cap only affects prediction players.
        if pos == "QB" and no_meaningful_stats:
            nil_value = min(nil_value, 1_000_000)
        # role_score-based QB cap: applies even if player has a few stats (true backups).
        # role_score < 10 ≈ < 30 pass attempts (spot duty / garbage time only).
        # role_score < 25 ≈ < 75 pass attempts (clear backup, < 6 games worth).
        # Exemption: elite social (soc_raw >= 80) captures high-brand non-starters
        #   like Arch Manning who command huge NIL before ever starting.
        if pos == "QB" and rs < 10 and soc_raw < 80:
            nil_value = min(nil_value, 700_000)
        elif pos == "QB" and rs < 25 and soc_raw < 75:
            nil_value = min(nil_value, 1_500_000)
        nil_value = round(nil_value, 2)

        results.append({
            "player_id":      player.id,
            "name":           player.name,
            "school":         player.school,
            "position":       player.position,
            "conference":     player.conference,
            "class_year":     getattr(player, "class_year", None),
            "recruit_score":  round(res.get("recruit_score", 20.0), 2),
            "formula_score":  round(composite, 2),
            "nil_value":      nil_value,
            "perf_score":     round(res["perf_score"], 2),
            "social_score":   round(res["social_score"], 2),
            "school_score":   round(res["school_score"], 2),
            "position_mult":  res["position_mult"],
            "conference_mult": res["conference_mult"],
        })

    df = pd.DataFrame(results).sort_values("nil_value", ascending=False).reset_index(drop=True)
    out_path = os.path.join(DATA_DIR, "nil_predictions_calibrated.csv")
    df.to_csv(out_path, index=False)
    print(f"Saved → {out_path}")

    print(f"\nTop 25 NIL predictions ({args.season} season):")
    print(f"  {'#':<4} {'Name':<28} {'School':<22} {'Pos':<5} {'Cls':<4} {'NIL Value':>12}  Score")
    print(f"  {'-'*85}")
    for i, row in df.head(25).iterrows():
        cy = row.get("class_year")
        cls = int(cy) if cy and not (isinstance(cy, float) and math.isnan(cy)) else "?"
        print(f"  {i+1:<4} {row['name']:<28} {(row['school'] or '?'):<22} "
              f"{(row['position'] or '?'):<5} {str(cls):<4} ${row['nil_value']:>11,.0f}  {row['formula_score']:.1f}")

    print(f"\nDistribution:")
    print(f"  Max:    ${df['nil_value'].max():>12,.0f}")
    print(f"  Median: ${df['nil_value'].median():>12,.0f}")
    print(f"  Min:    ${df['nil_value'].min():>12,.0f}")

    # Distribution sanity check — realistic NIL market breakdown
    print(f"\n  Value distribution across all {len(df):,} predictions:")
    dist_bands = [
        (">$2.5M",    2_500_000, float("inf")),
        ("$1M-$2.5M", 1_000_000, 2_500_000),
        ("$500K-$1M",   500_000, 1_000_000),
        ("$200K-$500K", 200_000,   500_000),
        ("$50K-$200K",   50_000,   200_000),
        ("<$50K",             0,    50_000),
    ]
    for label, lo, hi in dist_bands:
        cnt  = ((df["nil_value"] >= lo) & (df["nil_value"] < hi)).sum()
        pct  = cnt / len(df) * 100
        bar  = "█" * int(pct / 2)
        print(f"    {label:<14}: {cnt:>5,}  ({pct:4.1f}%)  {bar}")

    # Save calibration — store the scaler and raw inter_pairs/build info for reloading
    with open(CAL_PATH, "wb") as f:
        pickle.dump({
            "reg":            reg,
            "scaler":         best_scaler_v,
            "inter_pairs":    inter_pairs,
            "model_label":    best_label,
            "season":         args.season,
            "n_labeled":      len(matched_meta),
            "mape":           mape,
            "within_20_pct":  within_20_all_web,
            "spearman":       spear_r,
        }, f)
    print(f"\nCalibration saved → {CAL_PATH}")


if __name__ == "__main__":
    main()
