from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PlayerBase(BaseModel):
    name: str
    position: Optional[str] = None
    school: Optional[str] = None
    conference: Optional[str] = None
    season: Optional[int] = None
    recruiting_rating: Optional[float] = None
    recruiting_stars: Optional[int] = None

class PlayerCreate(PlayerBase):
    pass

class Player(PlayerBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SocialMediaBase(BaseModel):
    player_id: int
    player_name: Optional[str] = None
    instagram_followers: Optional[int] = None
    twitter_followers: Optional[int] = None
    total_followers: Optional[int] = None      # instagram + twitter
    engagement_rate: Optional[float] = None    # (likes+comments) / followers, as %
    avg_post_likes: Optional[int] = None
    verified_instagram: Optional[bool] = None
    verified_twitter: Optional[bool] = None
    last_updated: Optional[datetime] = None

class SocialMediaCreate(SocialMediaBase):
    pass

class SocialMedia(SocialMediaBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PerformanceStatsBase(BaseModel):
    player_id: int
    season: int
    player_name: Optional[str] = None
    school: Optional[str] = None
    total_yards: Optional[float] = None
    touchdowns: Optional[int] = None
    attempts: Optional[int] = None
    yards_per_game: Optional[float] = None
    usage_share: Optional[float] = None
    team_wins: Optional[int] = None
    efficiency_metric: Optional[float] = None

class PerformanceStatsCreate(PerformanceStatsBase):
    pass

class PerformanceStats(PerformanceStatsBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ValuationBase(BaseModel):
    player_id: int
    season: int
    nil_value: float
    perf_score: Optional[float] = None
    social_score: Optional[float] = None
    school_score: Optional[float] = None
    position_mult: Optional[float] = None
    conference_mult: Optional[float] = None

class ValuationCreate(ValuationBase):
    pass

class Valuation(ValuationBase):
    id: int
    computed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
