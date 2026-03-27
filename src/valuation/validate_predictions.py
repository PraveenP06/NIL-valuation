"""
Validate NIL model predictions against web-searched ground truth.

Samples 50 players from each of low / mid / high tier,
searches for real NIL valuations, and reports within-20% accuracy.

Excludes players already in nil_websearch.json (train/label set).

Usage:
    python src/valuation/validate_predictions.py
    python src/valuation/validate_predictions.py --per-tier 20   # quick run
"""
import os
import sys
import re
import json
import time
import argparse
import random

import pandas as pd
from ddgs import DDGS
from tqdm import tqdm

DATA_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
CSV_PATH  = os.path.join(DATA_DIR, "nil_predictions_calibrated.csv")
WEB_PATH  = os.path.join(DATA_DIR, "nil_websearch.json")
OUT_PATH  = os.path.join(DATA_DIR, "nil_validation_results.json")

SEARCH_DELAY = 1.5
NIL_MAX      = 7_000_000
MIN_LABEL    = 200_000   # don't try to web-validate $80K floor predictions

# Tier boundaries (predicted NIL value)
LOW_MAX  = 200_000
HIGH_MIN = 800_000

# --------------------------------------------------------------------------
# Dollar parser (same logic as pull_nil_valuations.py)
# --------------------------------------------------------------------------
_NIL_CONTEXT_RE = re.compile(
    r'\b(?:NIL|nil valuation|nil value|on3|opendorse|name image likeness|collective)\b',
    re.IGNORECASE,
)
_ON3_RE = re.compile(
    r'NIL\s+[Vv]aluation[:\s]+\$\s*([\d,.]+)\s*(?:million|M)\b'
    r'|\$\s*([\d,.]+)\s*(?:million|M)\b\s*NIL',
    re.IGNORECASE,
)
_MILLION_RE = re.compile(r'\$\s*([\d,.]+)\s*(?:million|M)\b', re.IGNORECASE)
_RANGE_RE   = re.compile(
    r'\$\s*([\d,.]+)\s*(?:million|M)?\s*[-–]\s*\$?\s*([\d,.]+)(?:\s*(?:million|M)\b)?',
    re.IGNORECASE,
)


def _float(raw: str) -> float:
    return float(raw.replace(',', ''))


def _in_range(d: float) -> bool:
    return 100_000 <= d <= NIL_MAX


def _has_nil_ctx(text: str, pos: int) -> bool:
    window = text[max(0, pos - 150): pos + 150]
    return bool(_NIL_CONTEXT_RE.search(window))


def _name_near(text: str, pos: int, full_name: str) -> bool:
    window = text[max(0, pos - 300): pos + 300]
    return full_name.lower() in window.lower()


def parse_nil_value(text: str, full_name: str = "") -> float | None:
    m = _ON3_RE.search(text)
    if m:
        raw = m.group(1) or m.group(2)
        val = _float(raw) * 1_000_000
        if _in_range(val):
            return round(val)

    m = _RANGE_RE.search(text)
    if m:
        lo = _float(m.group(1))
        hi = _float(m.group(2))
        if lo < 50:  lo *= 1_000_000
        if hi < 50:  hi *= 1_000_000
        if hi > lo > 100_000 and hi / lo < 5:
            mid = (lo + hi) / 2
            if _in_range(mid):
                has_ctx  = _has_nil_ctx(text, m.start())
                has_name = bool(full_name) and _name_near(text, m.start(), full_name)
                if has_ctx or has_name:
                    return round(mid)

    m = _MILLION_RE.search(text)
    if m and _has_nil_ctx(text, m.start()):
        val = _float(m.group(1)) * 1_000_000
        if _in_range(val):
            return round(val)

    return None


def search_nil(name: str, school: str) -> float | None:
    first, *rest = name.split()
    last = rest[-1] if rest else ""
    queries = [
        f'"{name}" NIL valuation site:on3.com',
        f'"{name}" "{school}" NIL valuation 2024 2025',
        f'"{first} {last}" "{school}" NIL value college football',
    ]
    for query in queries:
        try:
            results = DDGS().text(query, max_results=6)
            for r in (results or []):
                snippet = f"{r.get('title', '')} {r.get('body', '')}"
                snippet_low = snippet.lower()
                # Require BOTH full name (first+last) AND school in the snippet
                # to prevent false positives from players with common names.
                if last.lower() not in snippet_low:
                    continue
                if first.lower() not in snippet_low:
                    continue
                if school.lower().split()[0] not in snippet_low:   # at least first word of school name
                    continue
                val = parse_nil_value(snippet, full_name=name)
                if val is not None:
                    return val
        except Exception as e:
            tqdm.write(f"  DDG error ({name}): {e}")
        time.sleep(SEARCH_DELAY)
    return None


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def within_pct(pred: float, actual: float, pct: float = 0.20) -> bool:
    return abs(pred - actual) / actual <= pct


def main(per_tier: int = 50, seed: int = 99):
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} predictions from {CSV_PATH}")

    # Load existing labels to exclude from validation (don't test on training data)
    labeled_names: set[str] = set()
    if os.path.exists(WEB_PATH):
        with open(WEB_PATH) as f:
            for e in json.load(f):
                labeled_names.add(e["name"].lower())
    print(f"Excluding {len(labeled_names)} already-labeled players")

    df = df[~df["name"].str.lower().isin(labeled_names)]

    # Tier split
    low  = df[df["nil_value"] < LOW_MAX]
    mid  = df[(df["nil_value"] >= LOW_MAX) & (df["nil_value"] < HIGH_MIN)]
    high = df[df["nil_value"] >= HIGH_MIN]

    print(f"\nTier sizes (after exclusions): low={len(low)}, mid={len(mid)}, high={len(high)}")

    rng = random.Random(seed)

    def sample_tier(tier_df, n):
        rows = tier_df.to_dict("records")
        rng.shuffle(rows)
        return rows[:n]

    low_sample  = sample_tier(low,  per_tier)
    mid_sample  = sample_tier(mid,  per_tier)
    high_sample = sample_tier(high, per_tier)

    all_players = [
        ("low",  low_sample),
        ("mid",  mid_sample),
        ("high", high_sample),
    ]

    results = []
    tier_stats: dict[str, dict] = {t: {"total": 0, "found": 0, "within20": 0, "errors": []}
                                    for t in ("low", "mid", "high")}

    print(f"\nSearching {per_tier * 3} players across 3 tiers...\n")

    for tier_name, players in all_players:
        print(f"── {tier_name.upper()} tier ({len(players)} players) ──")
        for p in tqdm(players, desc=tier_name, unit="player"):
            pred = p["nil_value"]
            actual = search_nil(p["name"], p["school"])

            entry = {
                "tier":       tier_name,
                "name":       p["name"],
                "school":     p["school"],
                "position":   p.get("position", ""),
                "predicted":  pred,
                "actual":     actual,
                "within_20":  within_pct(pred, actual) if actual else None,
                "error_pct":  round(abs(pred - actual) / actual * 100, 1) if actual else None,
            }
            results.append(entry)

            ts = tier_stats[tier_name]
            ts["total"] += 1
            if actual is not None:
                ts["found"] += 1
                if within_pct(pred, actual):
                    ts["within20"] += 1
                else:
                    ts["errors"].append(
                        f"  {p['name']} ({p['school']}): pred=${pred:,.0f}  actual=${actual:,.0f}  "
                        f"err={entry['error_pct']:.0f}%"
                    )
                tqdm.write(
                    f"  {'✓' if entry['within_20'] else '✗'} {p['name']} ({p['school']}) "
                    f"pred=${pred:,.0f}  actual=${actual:,.0f}  err={entry['error_pct']:.0f}%"
                )
        print()

    # Save results
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    print("=" * 65)
    print("VALIDATION SUMMARY")
    print("=" * 65)
    total_found = total_within20 = 0
    for tier_name, ts in tier_stats.items():
        found    = ts["found"]
        within20 = ts["within20"]
        pct = within20 / found * 100 if found else 0
        tag = "✓" if pct >= 75 else "✗"
        print(f"  {tier_name.upper():5s}: {found}/{ts['total']} found  |  "
              f"within-20%: {within20}/{found} ({pct:.1f}%)  {tag}")
        total_found    += found
        total_within20 += within20

    overall = total_within20 / total_found * 100 if total_found else 0
    tag = "✓" if overall >= 75 else "✗"
    print(f"  {'TOTAL':5s}: {total_found}/{per_tier*3} found  |  "
          f"within-20%: {total_within20}/{total_found} ({overall:.1f}%)  {tag}")
    print()
    print(f"Target: ≥75% within-20%  |  Overall: {overall:.1f}%  {tag}")
    print(f"\nFull results → {OUT_PATH}")

    # Print missed predictions
    all_errors = [e for ts in tier_stats.values() for e in ts["errors"]]
    if all_errors:
        print(f"\nMissed predictions ({len(all_errors)}):")
        for err in all_errors:
            print(err)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-tier", type=int, default=50)
    parser.add_argument("--seed",     type=int, default=99)
    args = parser.parse_args()
    main(per_tier=args.per_tier, seed=args.seed)
