import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from fastapi import APIRouter, HTTPException, Query, Request
from api.limiter import limiter
from db.connection import get_client

router = APIRouter(prefix="/api/school", tags=["school"])
client = get_client()


@router.get("/{school}/top")
@limiter.limit("60/minute")
def get_school_top(
    request: Request,
    school: str,
    season: int = Query(2024),
    limit: int = Query(25, ge=1, le=100),
):
    rows = (
        client.table("valuations_with_players")
        .select("player_id,nil_value,name,position,school,conference,class_year")
        .eq("season", season)
        .eq("school", school)
        .order("nil_value", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No players found for school '{school}'")
    return {"school": school, "season": season, "data": rows}
