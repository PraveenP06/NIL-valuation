"""
Upsert calibrated NIL predictions into the Supabase valuations table.

Usage:
    python src/db/ingestion/upsert_valuations.py --season 2024
    python src/db/ingestion/upsert_valuations.py --season 2024 --dry-run
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
from tqdm import tqdm
from db.connection import get_client

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
CSV_PATH = os.path.join(DATA_DIR, "nil_predictions_calibrated.csv")


def main():
    parser = argparse.ArgumentParser(description="Upsert calibrated NIL predictions to Supabase")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    if not os.path.exists(CSV_PATH):
        print(f"ERROR: {CSV_PATH} not found. Run calibrate_model.py first.")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} predictions from {CSV_PATH}")

    client = get_client()
    success = errors = 0

    rows = df.to_dict("records")
    for i in tqdm(range(0, len(rows), args.batch_size), desc="Upserting"):
        chunk = rows[i:i + args.batch_size]
        records = [
            {
                "player_id":        int(r["player_id"]),
                "season":           args.season,
                "nil_value":        float(r["nil_value"]),
                "perf_score":       float(r["perf_score"])      if r.get("perf_score")      else None,
                "social_score":     float(r["social_score"])    if r.get("social_score")    else None,
                "school_score":     float(r["school_score"])    if r.get("school_score")    else None,
                "class_score":      float(r["class_score"])     if r.get("class_score")     else None,
                "recruit_score":    float(r["recruit_score"])   if r.get("recruit_score")   else None,
                "collective_score": float(r["collective_score"])if r.get("collective_score")else None,
                "position_mult":    float(r["position_mult"])   if r.get("position_mult")   else None,
                "conference_mult":  float(r["conference_mult"]) if r.get("conference_mult") else None,
            }
            for r in chunk
        ]
        if args.dry_run:
            print(f"  [DRY RUN] Would upsert {len(records)} records")
            success += len(records)
            continue
        try:
            client.table("valuations").upsert(
                records, on_conflict="player_id,season"
            ).execute()
            success += len(records)
        except Exception as e:
            tqdm.write(f"  Error on batch {i//args.batch_size}: {e}")
            errors += len(records)

    print(f"\n✅ Done! Upserted: {success} | Errors: {errors}")


if __name__ == "__main__":
    main()
