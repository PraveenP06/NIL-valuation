import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, HTTPException, Query, Request
from api.limiter import limiter
from db.connection import get_client

router = APIRouter(prefix="/api/valuations", tags=["valuations"])
client = get_client()

VIEW = "valuations_with_players"


@router.get("")
@limiter.limit("60/minute")
def list_valuations(
    request: Request,
    season: int = Query(2024),
    position: str = Query(None),
    conference: str = Query(None),
    class_year: int = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = (
        client.table(VIEW)
        .select("player_id,season,nil_value,perf_score,social_score,school_score,"
                "class_score,recruit_score,collective_score,position_mult,conference_mult,"
                "name,position,school,conference,class_year")
        .eq("season", season)
    )
    if position:
        query = query.eq("position", position)
    if conference:
        query = query.eq("conference", conference)
    if class_year is not None:
        query = query.eq("class_year", class_year)

    rows = (
        query
        .order("nil_value", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data or []
    )
    return {"data": rows, "limit": limit, "offset": offset, "season": season}


@router.get("/top")
@limiter.limit("60/minute")
def top_valuations(
    request: Request,
    season: int = Query(2024),
    limit: int = Query(25, ge=1, le=200),
):
    rows = (
        client.table(VIEW)
        .select("player_id,nil_value,name,position,school,conference,class_year")
        .eq("season", season)
        .order("nil_value", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )
    return {"data": rows, "season": season}


@router.get("/{player_id}")
@limiter.limit("60/minute")
def get_valuation(request: Request, player_id: int, season: int = Query(2024)):
    rows = (
        client.table(VIEW)
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
        raise HTTPException(status_code=404, detail="Valuation not found")
    return rows[0]
