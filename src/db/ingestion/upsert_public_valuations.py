"""
Upsert publicly known NIL valuations from JSON label files into the
public_valuations table.

Sources:
  - data/on3_rank_labels.json  (~3,796 entries, source="on3_rank_estimate")
  - data/nil_websearch.json    (~103 entries,   source="web_2025")

Usage:
    python src/db/ingestion/upsert_public_valuations.py --season 2024
    python src/db/ingestion/upsert_public_valuations.py --season 2024 --dry-run
"""
import os
import sys
import json
import re
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from db.connection import get_client

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data"))
SOURCES = [
    ("on3_rank_labels.json", "on3_rank_estimate"),
    ("nil_websearch.json",   "web_2025"),
]
SEASON = 2024


# ---------------------------------------------------------------------------
# Name normalisation (mirrors logic in other ingestion scripts)
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(
    r"\s+(jr\.?|sr\.?|ii+|iv|v|vi+)$", re.IGNORECASE
)
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_name(name: str) -> str:
    name = name.strip().lower()
    name = _PUNCT_RE.sub("", name)
    name = _SUFFIX_RE.sub("", name).strip()
    return name


def normalize_school(school: str) -> str:
    return school.strip().lower()


# ---------------------------------------------------------------------------
# Build lookup: (norm_name, norm_school) -> player_id
# ---------------------------------------------------------------------------

def build_lookup(client) -> dict[tuple[str, str], int]:
    """Fetch all players and return a (norm_name, norm_school) → id dict."""
    lookup: dict[tuple[str, str], int] = {}
    offset = 0
    batch = 1000
    while True:
        rows = (
            client.table("players")
            .select("id,name,school")
            .range(offset, offset + batch - 1)
            .execute()
            .data or []
        )
        for r in rows:
            key = (normalize_name(r["name"]), normalize_school(r["school"]))
            lookup[key] = r["id"]
        if len(rows) < batch:
            break
        offset += batch
    return lookup


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upsert public NIL valuations from JSON files"
    )
    parser.add_argument("--season", type=int, default=SEASON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = get_client()

    print("Building player lookup table...")
    lookup = build_lookup(client)
    print(f"  {len(lookup):,} players loaded")

    records: list[dict] = []
    unmatched: list[dict] = []

    for filename, source_tag in SOURCES:
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"  WARNING: {path} not found, skipping")
            continue

        entries = json.load(open(path))
        matched = 0
        for entry in entries:
            key = (normalize_name(entry["name"]), normalize_school(entry["school"]))
            player_id = lookup.get(key)
            if player_id is None:
                unmatched.append({"file": filename, **entry})
                continue
            records.append({
                "player_id": player_id,
                "season":    args.season,
                "nil_value": float(entry["nil_value"]),
                "source":    entry.get("source", source_tag),
            })
            matched += 1
        print(f"  {filename}: {matched}/{len(entries)} matched")

    # Deduplicate by (player_id, season, source) — keep highest nil_value
    deduped: dict[tuple, dict] = {}
    for r in records:
        key = (r["player_id"], r["season"], r["source"])
        if key not in deduped or r["nil_value"] > deduped[key]["nil_value"]:
            deduped[key] = r
    records = list(deduped.values())

    print(f"\nTotal records to upsert: {len(records)}")
    print(f"Unmatched entries:       {len(unmatched)}")

    if unmatched:
        unmatched_path = os.path.join(DATA_DIR, "public_valuations_unmatched.json")
        with open(unmatched_path, "w") as f:
            json.dump(unmatched, f, indent=2)
        print(f"Unmatched entries saved to: {unmatched_path}")

    if args.dry_run:
        print("\n[DRY RUN] No records written.")
        return

    if not records:
        print("Nothing to upsert.")
        return

    success = errors = 0
    BATCH = 100
    for i in range(0, len(records), BATCH):
        chunk = records[i : i + BATCH]
        try:
            client.table("public_valuations").upsert(
                chunk, on_conflict="player_id,season,source"
            ).execute()
            success += len(chunk)
        except Exception as e:
            print(f"  Error on batch {i // BATCH}: {e}")
            errors += len(chunk)

    print(f"\n✅ Done! Upserted: {success} | Errors: {errors}")


if __name__ == "__main__":
    main()
