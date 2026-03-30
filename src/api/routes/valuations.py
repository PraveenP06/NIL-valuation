import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from db.connection import get_client

router = APIRouter(prefix="/api/valuations", tags=["valuations"])
limiter = Limiter(key_func=get_remote_address)
client = get_client()


def _fetch_valuations_page(query, limit: int, offset: int) -> list[dict]:
    return (
        query
        .order("nil_value", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data or []
    )


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
        client.table("valuations")
        .select(
            "player_id, season, nil_value, perf_score, social_score, "
            "school_score, position_mult, conference_mult, "
            "players(name, position, school, conference, class_year)"
        )
        .eq("season", season)
    )

    if position:
        query = query.eq("players.position", position)
    if conference:
        query = query.eq("players.conference", conference)
    if class_year is not None:
        query = query.eq("players.class_year", class_year)

    rows = _fetch_valuations_page(query, limit, offset)
    return {"data": rows, "limit": limit, "offset": offset, "season": season}


@router.get("/{player_id}")
def get_valuation(player_id: int, season: int = Query(2024)):
    row = (
        client.table("valuations")
        .select(
            "player_id, season, nil_value, perf_score, social_score, "
            "school_score, position_mult, conference_mult, "
            "players(name, position, school, conference, class_year)"
        )
        .eq("player_id", player_id)
        .eq("season", season)
        .limit(1)
        .execute()
        .data
    )
    if not row:
        raise HTTPException(status_code=404, detail="Valuation not found")
    return row[0]
