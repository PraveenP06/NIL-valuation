import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, Query, Request
from api.limiter import limiter
from db.connection import get_client

router = APIRouter(prefix="/api/filters", tags=["filters"])
client = get_client()


@router.get("/meta")
@limiter.limit("30/minute")
def get_filter_meta(request: Request, season: int = Query(2024)):
    """Returns distinct positions, conferences, and schools for filter dropdowns.
    Only changes on re-ingestion so this is safe to cache aggressively on the frontend."""
    rows = (
        client.table("valuations_with_players")
        .select("position,conference,school")
        .eq("season", season)
        .execute()
        .data or []
    )

    positions   = sorted({r["position"]   for r in rows if r.get("position")})
    conferences = sorted({r["conference"] for r in rows if r.get("conference")})
    schools     = sorted({r["school"]     for r in rows if r.get("school")})

    return {
        "positions":   positions,
        "conferences": conferences,
        "schools":     schools,
    }
