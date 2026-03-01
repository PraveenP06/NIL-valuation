from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PlayerBase(BaseModel):
    name: str
    position: Optional[str] = None
    school: Optional[str] = None
    conference: Optional[str] = None
    recruiting_rating: Optional[float] = None
    recruiting_stars: Optional[int] = None

class PlayerCreate(PlayerBase):
    pass

class Player(PlayerBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
