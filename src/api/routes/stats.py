import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, Query
from db.connection import get_client

router = APIRouter(prefix="/api/stats", tags=["stats"])

client = get_client()


@router.get("")
def get_stats(season: int = Query(2024)):
    players_count = (
        client.table("players")
        .select("id", count="exact")
        .eq("season", season)
        .execute()
        .count
    ) or 0

    valuations_count = (
        client.table("valuations")
        .select("player_id", count="exact")
        .eq("season", season)
        .execute()
        .count
    ) or 0

    social_count = (
        client.table("social_media")
        .select("player_id", count="exact")
        .execute()
        .count
    ) or 0

    top = (
        client.table("valuations")
        .select("nil_value")
        .eq("season", season)
        .order("nil_value", desc=True)
        .limit(1)
        .execute()
        .data
    )

    return {
        "season": season,
        "players_count": players_count,
        "valuations_count": valuations_count,
        "social_data_count": social_count,
        "top_nil_value": top[0]["nil_value"] if top else None,
    }
