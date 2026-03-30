import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from db.connection import get_client

router = APIRouter(prefix="/api/players", tags=["players"])
limiter = Limiter(key_func=get_remote_address)
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
        .select("id, name, position, school, conference, class_year, season")
        .ilike("name", f"%{q}%")
    )
    if season is not None:
        query = query.eq("season", season)

    rows = query.limit(limit).execute().data or []
    return {"data": rows, "query": q}


@router.get("/{player_id}")
def get_player(player_id: int):
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
