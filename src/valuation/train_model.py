"""
Train NIL valuation model.

Strategy:
  - Primary: Ridge Regression on log10(nil_value) with labeled data
  - Fallback: Rank-based calibration mapping formula score → On3 dollar scale
  - Saves model + calibration curve to data/nil_model.pkl

Usage:
    python src/valuation/train_model.py
    python src/valuation/train_model.py --season 2023
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
from scipy.optimize import curve_fit
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import r2_score, mean_absolute_percentage_error

from db.crud import get_all_players, get_all_performance_stats_by_season, get_all_social_media
from valuation.model import (
    calculate_school_score, get_position_multiplier, get_conference_multiplier,
    calculate_performance_score, calculate_social_score, TIER1_SCHOOLS, TIER2_SCHOOLS,
)

DATA_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
MODEL_PATH = os.path.join(DATA_DIR, "nil_model.pkl")
SUPPL_PATH = os.path.join(DATA_DIR, "nil_supplement.json")
ON3_PATH   = os.path.join(DATA_DIR, "on3_rankings.json")

HS_KEYWORDS = {"high", "school", "prep", "academy", "little elm", "archbishop",
               "forest hills", "isidore", "west linn", "lake dallas",
               "martin luther king", "south florence", "st joseph", "chaminade"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())


def safe_log(x, floor=1.0) -> float:
    return math.log10(max(float(x or 0), floor))


def build_feature_vector(player, stats, social) -> np.ndarray:
    """5-feature vector: log_ig, log_total, school_score, pos_mult, conf_mult."""
    ig    = float(social.instagram_followers or 0) if social else 0.0
    tw    = float(social.twitter_followers or 0)   if social else 0.0
    total = ig + tw

    school_score = calculate_school_score(player)
    pos_mult     = get_position_multiplier(player.position)
    conf_mult    = get_conference_multiplier(player.conference)
    perf_score   = calculate_performance_score(stats)
    underclass   = 1.0 if getattr(player, "class_year", 0) in (1, 2) else 0.0

    return np.array([
        safe_log(ig),
        safe_log(total),
        school_score / 100.0,
        pos_mult,
        conf_mult,
        perf_score / 100.0,
        underclass,
    ], dtype=float)


FEATURE_NAMES = [
    "log_ig_followers",
    "log_total_followers",
    "school_score_norm",
    "pos_mult",
    "conf_mult",
    "perf_score_norm",
    "is_underclassman",
]


# ---------------------------------------------------------------------------
# Load labeled data
# ---------------------------------------------------------------------------

def load_labels() -> list[dict]:
    labels = []
    seen = set()

    # Supplement (manually curated)
    if os.path.exists(SUPPL_PATH):
        for p in json.load(open(SUPPL_PATH)):
            n = norm(p.get("name", ""))
            if n not in seen and p.get("nil_value"):
                seen.add(n)
                labels.append(p)

    # On3 scrape (cleaned)
    if os.path.exists(ON3_PATH):
        for p in json.load(open(ON3_PATH)):
            n = norm(p.get("name", ""))
            if (n not in seen
                    and p.get("nil_value")
                    and not any(kw in n for kw in HS_KEYWORDS)):
                seen.add(n)
                labels.append(p)

    return labels


# ---------------------------------------------------------------------------
# Match labels to DB players
# ---------------------------------------------------------------------------

def match_to_db(labels, players, stats_by_pid, social_by_pid):
    p_by_ns  = {(norm(p.name), norm(p.school or "")): p for p in players}
    p_by_name: dict[str, list] = {}
    for p in players:
        p_by_name.setdefault(norm(p.name), []).append(p)

    X, y, meta = [], [], []
    for lbl in labels:
        nn = norm(lbl.get("name", ""))
        ns = norm(lbl.get("school", ""))
        player = p_by_ns.get((nn, ns))
        if not player:
            cands = p_by_name.get(nn, [])
            player = cands[0] if len(cands) == 1 else None
        if not player:
            continue

        stats  = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)
        X.append(build_feature_vector(player, stats, social))
        y.append(math.log10(lbl["nil_value"]))
        meta.append({"name": player.name, "school": player.school,
                     "nil_value": lbl["nil_value"], "source": lbl.get("source")})

    return np.array(X), np.array(y), meta


# ---------------------------------------------------------------------------
# Ridge Regression with LOO-CV
# ---------------------------------------------------------------------------

def train_ridge(X, y, meta) -> tuple:
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    # Pick best alpha via LOO
    alphas = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
    model = RidgeCV(alphas=alphas, cv=LeaveOneOut())
    model.fit(Xs, y)

    print(f"\n  Best alpha: {model.alpha_}")
    print(f"  Intercept: {model.intercept_:.3f}  (= ${10**model.intercept_:,.0f})")
    print(f"  Coefficients:")
    for name, coef in zip(FEATURE_NAMES, model.coef_):
        print(f"    {name:<30} {coef:+.4f}")

    # LOO-CV predictions for accuracy reporting
    loo = LeaveOneOut()
    y_pred_loo = np.zeros(len(y))
    for train_idx, test_idx in loo.split(Xs):
        m = Ridge(alpha=model.alpha_)
        m.fit(Xs[train_idx], y[train_idx])
        y_pred_loo[test_idx] = m.predict(Xs[test_idx])

    # Metrics in log space
    r2  = r2_score(y, y_pred_loo)
    # Metrics in dollar space
    y_dollar      = 10 ** y
    y_pred_dollar = 10 ** y_pred_loo
    mape = mean_absolute_percentage_error(y_dollar, y_pred_dollar) * 100

    print(f"\n  LOO-CV R² (log scale): {r2:.3f}")
    print(f"  LOO-CV MAPE (dollars): {mape:.1f}%")
    print(f"  Target accuracy: <20% MAPE (>80% closeness)")

    print(f"\n  Per-player LOO predictions:")
    print(f"  {'Name':<25} {'Actual':>12} {'Predicted':>12} {'Error%':>8}")
    print(f"  {'-'*60}")
    for i, m in enumerate(meta):
        actual = 10 ** y[i]
        pred   = 10 ** y_pred_loo[i]
        err    = abs(pred - actual) / actual * 100
        print(f"  {m['name']:<25} ${actual:>11,.0f} ${pred:>11,.0f} {err:>7.1f}%")

    return model, scaler, r2, mape


# ---------------------------------------------------------------------------
# Rank-based calibration (fallback / supplement to Ridge)
# ---------------------------------------------------------------------------

def power_law(rank, a, b):
    return a * np.power(rank, b)


def build_rank_calibration(labels) -> tuple | None:
    """Fit rank → NIL value power law for rank-based fallback."""
    ranked = [(p["on3_rank"], p["nil_value"])
              for p in labels if p.get("on3_rank") and p.get("nil_value")]
    if len(ranked) < 5:
        return None
    ranked.sort()
    ranks  = np.array([r[0] for r in ranked], dtype=float)
    values = np.array([r[1] for r in ranked], dtype=float)
    try:
        popt, _ = curve_fit(power_law, ranks, values, p0=[5_000_000, -0.8], maxfev=5000)
        return tuple(popt)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Apply model to all DB players
# ---------------------------------------------------------------------------

def predict_all(model, scaler, players, stats_by_pid, social_by_pid) -> list[dict]:
    results = []
    for player in players:
        stats  = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)
        x = build_feature_vector(player, stats, social).reshape(1, -1)
        xs = scaler.transform(x)
        log_val = model.predict(xs)[0]
        nil_value = 10 ** log_val
        results.append({
            "player_id":     player.id,
            "name":          player.name,
            "school":        player.school,
            "position":      player.position,
            "conference":    player.conference,
            "nil_value":     round(nil_value, 2),
            "log_nil":       round(log_val, 4),
        })
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train NIL valuation model")
    parser.add_argument("--season", type=int, default=2023)
    args = parser.parse_args()

    print("Loading labels...")
    labels = load_labels()
    print(f"  {len(labels)} labeled players total")

    print(f"\nLoading DB for season {args.season}...")
    players  = [p for p in get_all_players() if p.season == args.season]
    stats_l  = get_all_performance_stats_by_season(args.season)
    social_l = get_all_social_media()
    stats_by_pid  = {s.player_id: s for s in stats_l}
    social_by_pid = {s.player_id: s for s in social_l}
    print(f"  {len(players)} players, {len(stats_l)} stats, {len(social_l)} social rows")

    print("\nMatching labels to DB players...")
    X, y, meta = match_to_db(labels, players, stats_by_pid, social_by_pid)
    print(f"  Matched: {len(meta)} players")

    if len(meta) < 5:
        print("ERROR: Need at least 5 matched labeled players to train.")
        sys.exit(1)

    print("\nTraining Ridge Regression (log-scale target)...")
    model, scaler, r2, mape = train_ridge(X, y, meta)

    # Rank calibration
    rank_curve = build_rank_calibration(labels)
    if rank_curve:
        print(f"\n  Rank curve: NIL ≈ ${rank_curve[0]:,.0f} × rank^{rank_curve[1]:.3f}")

    # Save model bundle
    bundle = {
        "model":       model,
        "scaler":      scaler,
        "feature_names": FEATURE_NAMES,
        "rank_curve":  rank_curve,
        "season":      args.season,
        "n_train":     len(meta),
        "loo_r2":      r2,
        "loo_mape":    mape,
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)
    print(f"\nModel saved → {MODEL_PATH}")

    # Predict all players and save CSV
    print(f"\nPredicting all {len(players)} players...")
    results = predict_all(model, scaler, players, stats_by_pid, social_by_pid)
    df = pd.DataFrame(results).sort_values("nil_value", ascending=False)
    out_path = os.path.join(DATA_DIR, "nil_predictions.csv")
    df.to_csv(out_path, index=False)
    print(f"Saved → {out_path}")

    print(f"\nTop 20 predicted NIL values for {args.season} season:")
    print(f"  {'Name':<28} {'School':<22} {'Pos':<5} {'NIL Value':>12}")
    print(f"  {'-'*70}")
    for _, row in df.head(20).iterrows():
        print(f"  {row['name']:<28} {(row['school'] or '?'):<22} "
              f"{(row['position'] or '?'):<5} ${row['nil_value']:>11,.0f}")

    # Summary stats
    print(f"\nDistribution:")
    print(f"  Max:    ${df['nil_value'].max():>12,.0f}")
    print(f"  Median: ${df['nil_value'].median():>12,.0f}")
    print(f"  Min:    ${df['nil_value'].min():>12,.0f}")


if __name__ == "__main__":
    main()
