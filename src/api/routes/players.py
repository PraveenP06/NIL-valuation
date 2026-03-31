import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, HTTPException, Query, Request
from api.limiter import limiter
from db.connection import get_client

router = APIRouter(prefix="/api/players", tags=["players"])
client = get_client()


@router.get("/search")
@limiter.limit("30/minute")
def search_players(
    request: Request,
    q: str = Query(..., min_length=2),
    season: int = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    query = (
        client.table("players")
        .select("id,name,position,school,conference,class_year,season")
        .ilike("name", f"%{q}%")
    )
    if season is not None:
        query = query.eq("season", season)

    rows = query.limit(limit).execute().data or []
    return {"data": rows, "query": q}


@router.get("/{player_id}/valuation")
@limiter.limit("60/minute")
def get_player_valuation(request: Request, player_id: int, season: int = Query(2024)):
    """Combined player + full score breakdown — used by the player detail page."""
    rows = (
        client.table("valuations_with_players")
        .select("player_id,season,nil_value,perf_score,social_score,school_score,"
                "class_score,recruit_score,collective_score,position_mult,conference_mult,"
                "name,position,school,conference,class_year")
        .eq("player_id", player_id)
        .eq("season", season)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Player valuation not found")

    result = rows[0]

    # Attach all public valuations for this player (sorted by nil_value desc)
    pub_rows = (
        client.table("public_valuations")
        .select("nil_value,source,scraped_at")
        .eq("player_id", player_id)
        .eq("season", season)
        .order("nil_value", desc=True)
        .execute()
        .data or []
    )
    result["public_valuations"] = pub_rows

    return result


@router.get("/{player_id}")
@limiter.limit("60/minute")
def get_player(request: Request, player_id: int):
    rows = (
        client.table("players")
        .select("*")
        .eq("id", player_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Player not found")
    return rows[0]
