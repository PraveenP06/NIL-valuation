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
from sklearn.linear_model import HuberRegressor
from sklearn.metrics import mean_absolute_percentage_error

from db.crud import get_all_players, get_all_performance_stats_by_season, get_all_social_media
from valuation.model import estimate_nil_value

DATA_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
SUPPL_PATH = os.path.join(DATA_DIR, "nil_supplement.json")
ON3_PATH   = os.path.join(DATA_DIR, "on3_rankings.json")
CAL_PATH   = os.path.join(DATA_DIR, "calibration.pkl")

HS_KEYWORDS = {"high", "school", "prep", "academy", "little elm", "archbishop",
               "forest hills", "isidore", "west linn", "lake dallas",
               "martin luther king", "south florence", "st joseph", "chaminade"}


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s).strip()
    return " ".join(s.split())


def load_labels() -> list[dict]:
    labels = []
    seen: set[tuple] = set()
    for path in [SUPPL_PATH, ON3_PATH]:
        if not os.path.exists(path):
            continue
        for p in json.load(open(path)):
            n = norm(p.get("name", ""))
            s = norm(p.get("school", "") or "")
            key = (n, s) if s else (n, "")
            if key not in seen and p.get("nil_value") and not any(kw in n for kw in HS_KEYWORDS):
                seen.add(key)
                labels.append(p)
    return labels


def main():
    parser = argparse.ArgumentParser(description="Calibrate NIL formula to real dollar amounts")
    parser.add_argument("--season", type=int, default=2024)
    args = parser.parse_args()

    print("Loading labels...")
    labels = load_labels()
    print(f"  {len(labels)} labeled players")

    print(f"\nLoading DB for season {args.season}...")
    all_players = get_all_players()
    players     = [p for p in all_players if p.season == args.season]
    stats_l     = get_all_performance_stats_by_season(args.season)
    social_l    = get_all_social_media()
    stats_by_pid  = {s.player_id: s for s in stats_l}
    social_by_pid = {s.player_id: s for s in social_l}
    print(f"  {len(players)} players, {len(stats_l)} stats, {len(social_l)} social rows")

    # Build lookups
    p_by_ns: dict[tuple, object] = {(norm(p.name), norm(p.school or "")): p for p in players}
    p_by_name: dict[str, list] = {}
    for p in players:
        p_by_name.setdefault(norm(p.name), []).append(p)

    # --- Match labels to DB, compute formula score for each ---
    print("\nMatching labels and computing formula scores...")
    matched_scores, matched_nil, matched_meta = [], [], []

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
        result = estimate_nil_value(player, stats, social, base_value=100.0)  # base=100 → get 0-100 score

        # composite score (0-100)
        composite = (
            result["perf_score"]   * 0.30 +
            result["social_score"] * 0.25 +
            result["school_score"] * 0.20 +
            ((result["position_mult"] - 0.7) / (1.5 - 0.7) * 100) * 0.15 +
            ((result["conference_mult"] - 0.8) / (1.3 - 0.8) * 100) * 0.10
        )
        matched_scores.append(composite)
        matched_nil.append(lbl["nil_value"])
        matched_meta.append({
            "name": player.name, "school": player.school,
            "position": player.position,
            "formula_score": composite,
            "actual_nil": lbl["nil_value"],
            "source": lbl.get("source", ""),
        })

    print(f"  Matched: {len(matched_meta)} players")

    if len(matched_meta) < 5:
        print("ERROR: Need at least 5 matched players.")
        sys.exit(1)

    X = np.array(matched_scores).reshape(-1, 1)
    y = np.array([math.log10(v) for v in matched_nil])

    # --- Fit Huber regression (robust to outliers) in log space ---
    # log10(nil) = a * formula_score + b
    reg = HuberRegressor(epsilon=1.5, max_iter=500)
    reg.fit(X, y)

    print(f"\n  Calibration: log10(NIL) = {reg.coef_[0]:.4f} × score + {reg.intercept_:.4f}")
    print(f"  At score=0:   ${10**reg.intercept_:>12,.0f}")
    print(f"  At score=50:  ${10**(reg.coef_[0]*50 + reg.intercept_):>12,.0f}")
    print(f"  At score=100: ${10**(reg.coef_[0]*100 + reg.intercept_):>12,.0f}")

    # --- In-sample accuracy ---
    y_pred_log = reg.predict(X)
    y_actual   = np.array(matched_nil)
    y_pred     = 10 ** y_pred_log
    mape = mean_absolute_percentage_error(y_actual, y_pred) * 100
    spear_r, spear_p = spearmanr(y_actual, y_pred)

    print(f"\n  In-sample MAPE:             {mape:.1f}%")
    print(f"  Spearman rank correlation:  {spear_r:.3f} (p={spear_p:.4f})")
    print(f"  Target: MAPE <20% (>80% accuracy), Spearman >0.8")

    print(f"\n  Per-player calibrated predictions:")
    print(f"  {'Name':<25} {'Actual':>12} {'Predicted':>12} {'Error%':>8} Source")
    print(f"  {'-'*70}")
    for i, m in enumerate(matched_meta):
        err = abs(y_pred[i] - m["actual_nil"]) / m["actual_nil"] * 100
        print(f"  {m['name']:<25} ${m['actual_nil']:>11,.0f} ${y_pred[i]:>11,.0f} "
              f"{err:>7.1f}%  {m['source']}")

    # --- Apply calibration to ALL players ---
    print(f"\nApplying calibration to all {len(players)} players...")
    results = []
    for player in players:
        if getattr(player, "nfl_drafted_2024", False):
            continue
        stats  = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)
        res    = estimate_nil_value(player, stats, social, base_value=100.0)

        composite = (
            res["perf_score"]   * 0.30 +
            res["social_score"] * 0.25 +
            res["school_score"] * 0.20 +
            ((res["position_mult"] - 0.7) / (1.5 - 0.7) * 100) * 0.15 +
            ((res["conference_mult"] - 0.8) / (1.3 - 0.8) * 100) * 0.10
        )
        log_nil   = reg.predict([[composite]])[0]
        nil_value = round(10 ** log_nil, 2)

        results.append({
            "player_id":     player.id,
            "name":          player.name,
            "school":        player.school,
            "position":      player.position,
            "conference":    player.conference,
            "class_year":    getattr(player, "class_year", None),
            "formula_score": round(composite, 2),
            "nil_value":     nil_value,
            "perf_score":    round(res["perf_score"], 2),
            "social_score":  round(res["social_score"], 2),
            "school_score":  round(res["school_score"], 2),
            "position_mult": res["position_mult"],
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

    # Save calibration
    with open(CAL_PATH, "wb") as f:
        pickle.dump({"reg": reg, "season": args.season,
                     "n_labeled": len(matched_meta),
                     "mape": mape, "spearman": spear_r}, f)
    print(f"\nCalibration saved → {CAL_PATH}")


if __name__ == "__main__":
    main()
