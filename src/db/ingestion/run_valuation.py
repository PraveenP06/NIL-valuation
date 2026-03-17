"""
Batch valuation script — computes and stores NIL valuations for all players.

Usage:
    python src/db/ingestion/run_valuation.py --season 2023
    python src/db/ingestion/run_valuation.py --season 2023 --max-players 50
    python src/db/ingestion/run_valuation.py --season 2023 --school "Alabama"
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.crud import (
    get_all_players,
    get_all_performance_stats_by_season,
    get_all_social_media,
    upsert_valuation,
)
from db.models import ValuationCreate
from valuation.model import estimate_nil_value


def main():
    parser = argparse.ArgumentParser(description="Compute and store NIL valuations")
    parser.add_argument("--season", type=int, required=True, help="Season year (e.g. 2023)")
    parser.add_argument("--max-players", type=int, default=None, help="Debug cap on number of players")
    parser.add_argument("--school", type=str, default=None, help="Scope to a single school")
    args = parser.parse_args()

    print(f"Fetching all players...")
    players = get_all_players()
    print(f"  {len(players)} total players")

    if args.school:
        players = [p for p in players if (p.school or "").lower() == args.school.lower()]
        print(f"  Filtered to {len(players)} players at '{args.school}'")

    # Only keep players with the right season or no season set
    players = [p for p in players if p.season is None or p.season == args.season]
    print(f"  {len(players)} players for season {args.season}")

    if args.max_players:
        players = players[:args.max_players]
        print(f"  Capped at {args.max_players} for this run")

    print(f"\nFetching performance stats for {args.season}...")
    stats_list = get_all_performance_stats_by_season(args.season)
    stats_by_pid = {s.player_id: s for s in stats_list}
    print(f"  {len(stats_by_pid)} stat rows loaded")

    print(f"Fetching social media data...")
    social_list = get_all_social_media()
    social_by_pid = {s.player_id: s for s in social_list}
    print(f"  {len(social_by_pid)} social rows loaded")

    print(f"\nComputing valuations...")
    total_computed = 0
    total_skipped = 0
    total_errors = 0
    batch: list[ValuationCreate] = []

    for player in players:
        stats = stats_by_pid.get(player.id)
        social = social_by_pid.get(player.id)

        # Skip players with no stats and no social presence (no signal)
        if stats is None and social is None:
            total_skipped += 1
            continue

        # Ensure player has a season set for the valuation record
        if player.season is None:
            player = player.copy(update={"season": args.season})

        try:
            result = estimate_nil_value(player, stats, social)
            result["season"] = args.season  # always use the requested season
            v = ValuationCreate(**result)
            batch.append(v)
        except Exception as e:
            print(f"  ERROR computing {player.name} (id={player.id}): {e}")
            total_errors += 1
            continue

        if len(batch) >= 100:
            _flush_batch(batch)
            total_computed += len(batch)
            batch = []

    if batch:
        _flush_batch(batch)
        total_computed += len(batch)

    print(f"\n✅ Done!")
    print(f"  Computed & stored: {total_computed}")
    print(f"  Skipped (no data): {total_skipped}")
    print(f"  Errors:            {total_errors}")


def _flush_batch(batch: list[ValuationCreate]):
    for v in batch:
        try:
            upsert_valuation(v)
        except Exception as e:
            print(f"  DB error upserting player_id={v.player_id}: {e}")


if __name__ == "__main__":
    main()
