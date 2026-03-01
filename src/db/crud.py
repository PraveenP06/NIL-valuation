from connection import get_client
from models import Player, PlayerCreate
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
    response = client.table("players").select("*").execute()
    
    return [Player(**player) for player in response.data] if response.data else []

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
