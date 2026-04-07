import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, Query, Request
from api.limiter import limiter
from db.connection import get_client

router = APIRouter(prefix="/api/stats", tags=["stats"])

client = get_client()


@router.get("")
@limiter.limit("30/minute")
def get_stats(request: Request, season: int = Query(2025)):
    row = client.rpc("get_season_stats", {"p_season": season}).execute().data
    if not row:
        return {
            "season": season,
            "players_count": 0,
            "valuations_count": 0,
            "social_data_count": 0,
            "top_nil_value": None,
        }
    r = row[0]
    return {
        "season": season,
        "players_count": r["players_count"],
        "valuations_count": r["valuations_count"],
        "social_data_count": r["social_data_count"],
        "top_nil_value": r["top_nil_value"],
    }
