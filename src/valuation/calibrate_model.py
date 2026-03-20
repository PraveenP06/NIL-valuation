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


def _feature_vector(res: dict, position: str = "") -> list[float]:
    """Extract 12 normalised features from estimate_nil_value() result dict.

    Base 8 + has_stats + is_QB + social_tier + social×nonQB:
      is_QB: binary 100/0 — QBs earn 2-3× non-QBs for same features.
      social_tier: bucketed social score capturing non-linear follower jumps.
      social×nonQB: for non-QBs, social following dominates NIL value.
        A WR with 300K followers earns more than a WR with 10K regardless
        of school prestige. This term lets the model learn that without
        being confused by QB data where social matters less.
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
            soc_tier]


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
    # Instead of using noisy power-law dollar estimates, we bucket On3 ranks
    # into 4 bands and assign conservative anchor values (band midpoints).
    # Each band contributes ~12 sampled players at low weight (1.0 vs curated 5.0).
    # This teaches the model the shape of the low/mid tier without overwhelming
    # the curated high-tier labels.
    RANK_BANDS = [
        # (rank_lo, rank_hi, anchor_value, per_band_cap)
        (26,   100,   1_500_000, 8),    # P4 starters, national visibility
        (101,  300,     800_000, 8),    # solid starters, regional recognition
        (301,  1000,    400_000, 8),    # roster contributors
        (1001, 99999,   180_000, 8),    # depth players, walk-ons
    ]
    if os.path.exists(RANK_PATH):
        rank_labels = json.load(open(RANK_PATH))
        # Sort by rank ascending (best first)
        rank_labels.sort(key=lambda x: x.get("rank") or 99999)

        import random as _random
        _random.seed(7)

        total_anchors = 0
        for (rlo, rhi, anchor_val, cap) in RANK_BANDS:
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
    print("\nMatching labels and extracting features (cross-season)...")
    matched_features, matched_nil, matched_meta = [], [], []

    for lbl in labels:
        nn = norm(lbl.get("name", ""))
        ns = norm(lbl.get("school", ""))

        # Try primary season first
        player = p_by_ns.get((nn, ns))
        if not player:
            cands = p_by_name.get(nn, [])
            player = cands[0] if len(cands) == 1 else None

        used_season = args.season
        stats_map   = stats_by_pid

        # Fall back to other season
        if not player:
            player = p_by_ns_other.get((nn, ns))
            if not player:
                cands = p_by_name_other.get(nn, [])
                player = cands[0] if len(cands) == 1 else None
            if player:
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

        fvec = _feature_vector(res, position=player.position or "")
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
            # Curated (web_2025) = 5×, rank-tier anchors = 1×, DDG-scraped = 0 (not trusted yet)
            "weight":       5.0 if src == "web_2025" else (1.0 if src == "rank_anchor" else 0.0),
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
    feature_names = ["perf", "social", "school", "position", "conference", "class_year", "recruit", "collective", "has_stats", "is_QB", "social_tier"]
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
    ]

    best_w20, best_reg, best_label = -1, None, None
    best_build_fn  = variants[0][3]
    best_scaler_v  = scaler_base
    best_names     = feature_names
    best_tag       = "base"

    eps_values = [round(1.0 + e * 0.05, 2) for e in range(11)] + [1.55, 1.6, 1.7, 1.8, 2.0, 3.0]
    alpha_ridge = [0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0]
    alpha_inter = [1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]

    # inter3 has an extra interaction term (5 total) — use stronger regularization
    alpha_inter3 = [50.0, 100.0, 500.0, 1000.0, 2000.0]

    for (X_v, sc_v, _, build_fn, names_v, tag) in variants:
        alphas = alpha_inter3 if tag == "inter3" else (alpha_inter if tag in ("inter", "inter2") else alpha_ridge)
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
    all_web_mask = sample_weights >= 2.0   # original + DDG-scraped
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

        fvec      = _feature_vector(res, position=player.position or "")
        # Formula composite score (0-100): perf 20%, social 20%, school 15%, pos 12%, conf 8%, class 5%, recruit 20%
        # ML-only features (collective, has_stats, is_QB, social_tier, social×nonQB) get 0 weight in display score
        composite = sum(f * w for f, w in zip(fvec, [0.20, 0.20, 0.15, 0.12, 0.08, 0.05, 0.20, 0.0, 0.0, 0.0, 0.0]))
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
        if composite < 42:
            nil_value = min(nil_value, 1_500_000)
        elif composite < 55:
            nil_value = min(nil_value, 3_000_000)
        # Extra cap for no-stats players (walk-ons/non-contributors) without top recruit status
        if perf_val == 0 and recruit_val < 60:
            nil_value = min(nil_value, 2_000_000)
        # Position-group ceilings (Phase 2): non-QB positions have lower NIL ceilings.
        # Only the rarest exceptions (Jeremiah Smith-tier) exceed these.
        pos = (player.position or "").upper()
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
        elif pos in ("K", "P", "PK", "LS", "ST"):  # PK = placekicker
            nil_value = min(nil_value, 1_000_000)
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
