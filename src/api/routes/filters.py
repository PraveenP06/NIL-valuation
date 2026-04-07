import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from functools import lru_cache
from fastapi import APIRouter, Query, Request
from api.limiter import limiter
from db.connection import get_client

router = APIRouter(prefix="/api/filters", tags=["filters"])
client = get_client()


@lru_cache(maxsize=8)
def _fetch_filter_meta(season: int) -> dict:
    """Cached — filters only change on re-ingestion (~weekly)."""
    rows = (
        client.table("valuations_with_players")
        .select("position,conference,school")
        .eq("season", season)
        .execute()
        .data or []
    )
    return {
        "positions":   sorted({r["position"]   for r in rows if r.get("position")}),
        "conferences": sorted({r["conference"] for r in rows if r.get("conference")}),
        "schools":     sorted({r["school"]     for r in rows if r.get("school")}),
    }


@router.get("/meta")
@limiter.limit("30/minute")
def get_filter_meta(request: Request, season: int = Query(2025)):
    """Returns distinct positions, conferences, and schools for filter dropdowns."""
    return _fetch_filter_meta(season)
