import os
import sys
import argparse
# PRUNE PLAYERS — two-phase cleanup:
#   Phase 1: remove players with no performance_stats row
#   Phase 2: remove players with no social_media row
# Always run --dry-run first to preview what will be deleted.

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
from db.connection import get_client

load_dotenv()


def fetch_all_ids(client, table: str, column: str = "id") -> set[int]:
    page_size = 1000
    start = 0
    ids = set()
    while True:
        rows = client.table(table).select(column).range(start, start + page_size - 1).execute().data or []
        for row in rows:
            ids.add(row[column])
        if len(rows) < page_size:
            break
        start += page_size
    return ids


def fetch_matched_player_ids(client, table: str) -> set[int]:
    """Return the set of player_ids that appear in the given table."""
    page_size = 1000
    start = 0
    ids = set()
    while True:
        rows = client.table(table).select("player_id").range(start, start + page_size - 1).execute().data or []
        for row in rows:
            ids.add(row["player_id"])
        if len(rows) < page_size:
            break
        start += page_size
    return ids


def delete_players(client, ids: list[int], dry_run: bool):
    if not ids:
        print("  Nothing to delete.")
        return
    if dry_run:
        print(f"  [DRY RUN] Would delete {len(ids)} players.")
        return

    batch_size = 200
    deleted = 0
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        client.table("players").delete().in_("id", chunk).execute()
        deleted += len(chunk)
    print(f"  Deleted {deleted} players.")


def phase1_stats(client, dry_run: bool):
    print("\n--- Phase 1: Remove players with no performance stats ---")
    all_player_ids = fetch_all_ids(client, "players")
    matched_ids = fetch_matched_player_ids(client, "performance_stats")
    unmatched = sorted(all_player_ids - matched_ids)
    print(f"  Total players:       {len(all_player_ids)}")
    print(f"  With stats:          {len(matched_ids)}")
    print(f"  Without stats:       {len(unmatched)}")
    delete_players(client, unmatched, dry_run)


def phase2_social(client, dry_run: bool):
    print("\n--- Phase 2: Remove players with no social media data ---")
    all_player_ids = fetch_all_ids(client, "players")
    matched_ids = fetch_matched_player_ids(client, "social_media")
    unmatched = sorted(all_player_ids - matched_ids)
    print(f"  Total players:       {len(all_player_ids)}")
    print(f"  With social media:   {len(matched_ids)}")
    print(f"  Without social data: {len(unmatched)}")
    delete_players(client, unmatched, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prune players not matched to stats or social media")
    parser.add_argument("--phase", type=int, choices=[1, 2], default=None,
                        help="Run only phase 1 (stats) or phase 2 (social). Omit to run both.")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview deletions without making changes (default: True)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform the deletions (overrides --dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute
    if dry_run:
        print("🔍 DRY RUN — pass --execute to apply deletions\n")
    else:
        print("⚠️  EXECUTE MODE — deletions are permanent\n")

    client = get_client()

    if args.phase == 1:
        phase1_stats(client, dry_run)
    elif args.phase == 2:
        phase2_social(client, dry_run)
    else:
        phase1_stats(client, dry_run)
        phase2_social(client, dry_run)

    print("\nDone.")
