import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from connection import get_client
from models import Player, PlayerCreate, PerformanceStats, PerformanceStatsCreate, SocialMedia, SocialMediaCreate
from typing import List, Optional

client = get_client()

def create_player(player: PlayerCreate) -> Player:
    """Insert a new player into the database"""
    player_data = player.dict()
    response = client.table("players").insert(player_data).execute()
    
    if response.data:
        return Player(**response.data[0])
    raise Exception("Failed to create player")

def get_player(player_id: int) -> Optional[Player]:
    """Fetch a single player by ID"""
    response = client.table("players").select("*").eq("id", player_id).execute()
    
    if response.data:
        return Player(**response.data[0])
    return None

def get_all_players() -> List[Player]:
    """Fetch all players from the database"""
    page_size = 1000
    start = 0
    all_rows = []

    while True:
        end = start + page_size - 1
        response = client.table("players").select("*").range(start, end).execute()
        rows = response.data or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size

    return [Player(**player) for player in all_rows]

def update_player(player_id: int, player: PlayerCreate) -> Optional[Player]:
    """Update a player by ID"""
    player_data = player.dict(exclude_unset=True)
    response = client.table("players").update(player_data).eq("id", player_id).execute()
    
    if response.data:
        return Player(**response.data[0])
    return None

def delete_player(player_id: int) -> bool:
    """Delete a player by ID"""
    response = client.table("players").delete().eq("id", player_id).execute()
    return len(response.data) > 0 if response.data else True

def get_players_by_school(school: str) -> List[Player]:
    """Fetch all players from a specific school"""
    response = client.table("players").select("*").eq("school", school).execute()
    
    return [Player(**player) for player in response.data] if response.data else []

def get_players_by_conference(conference: str) -> List[Player]:
    """Fetch all players from a specific conference"""
    response = client.table("players").select("*").eq("conference", conference).execute()
    
    return [Player(**player) for player in response.data] if response.data else []


# ============================================================================
# PERFORMANCE STATS CRUD OPERATIONS
# ============================================================================

def create_performance_stats(stats: PerformanceStatsCreate) -> PerformanceStats:
    """Insert new performance statistics for a player"""
    stats_data = stats.dict()
    response = client.table("performance_stats").insert(stats_data).execute()
    
    if response.data:
        return PerformanceStats(**response.data[0])
    raise Exception("Failed to create performance stats")

def get_performance_stats(stats_id: int) -> Optional[PerformanceStats]:
    """Fetch performance stats by ID"""
    response = client.table("performance_stats").select("*").eq("id", stats_id).execute()
    
    if response.data:
        return PerformanceStats(**response.data[0])
    return None

def get_stats_by_player(player_id: int) -> List[PerformanceStats]:
    """Fetch all performance stats for a specific player"""
    response = client.table("performance_stats").select("*").eq("player_id", player_id).execute()
    
    return [PerformanceStats(**stat) for stat in response.data] if response.data else []

def get_stats_by_player_season(player_id: int, season: int) -> Optional[PerformanceStats]:
    """Fetch performance stats for a player in a specific season"""
    response = client.table("performance_stats").select("*").eq("player_id", player_id).eq("season", season).execute()
    
    if response.data:
        return PerformanceStats(**response.data[0])
    return None

def update_performance_stats(stats_id: int, stats: PerformanceStatsCreate) -> Optional[PerformanceStats]:
    """Update performance stats by ID"""
    stats_data = stats.dict(exclude_unset=True)
    response = client.table("performance_stats").update(stats_data).eq("id", stats_id).execute()
    
    if response.data:
        return PerformanceStats(**response.data[0])
    return None

def delete_performance_stats(stats_id: int) -> bool:
    """Delete performance stats by ID"""
    response = client.table("performance_stats").delete().eq("id", stats_id).execute()
    return len(response.data) > 0 if response.data else True

def get_top_performers_by_season(season: int, metric: str = "total_yards", limit: int = 10) -> List[PerformanceStats]:
    """Fetch top performers for a specific season by a given metric"""
    response = client.table("performance_stats").select("*").eq("season", season).order(metric, desc=True).limit(limit).execute()

    return [PerformanceStats(**stat) for stat in response.data] if response.data else []


# ============================================================================
# SOCIAL MEDIA CRUD OPERATIONS
# ============================================================================

def upsert_social_media(social: SocialMediaCreate) -> SocialMedia:
    """Insert or update social media data for a player (unique on player_id)"""
    data = social.dict()
    response = client.table("social_media").upsert(data, on_conflict="player_id").execute()
    if response.data:
        return SocialMedia(**response.data[0])
    raise Exception("Failed to upsert social media data")

def get_social_media(player_id: int) -> Optional[SocialMedia]:
    """Fetch social media data for a player"""
    response = client.table("social_media").select("*").eq("player_id", player_id).execute()
    if response.data:
        return SocialMedia(**response.data[0])
    return None

def get_top_social_by_followers(limit: int = 10) -> List[SocialMedia]:
    """Fetch players ranked by total followers"""
    response = client.table("social_media").select("*").order("total_followers", desc=True).limit(limit).execute()
    return [SocialMedia(**row) for row in response.data] if response.data else []

def delete_social_media(player_id: int) -> bool:
    """Delete social media data for a player"""
    response = client.table("social_media").delete().eq("player_id", player_id).execute()
    return len(response.data) > 0 if response.data else True
