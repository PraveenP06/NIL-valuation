"""
Test script to demonstrate CRUD operations with Supabase
"""
from crud import (
    create_player,
    get_player,
    get_all_players,
    update_player,
    delete_player,
    get_players_by_school,
    get_players_by_conference
)
from models import PlayerCreate

# Example 1: Create a new player
print("=" * 50)
print("Creating a new player...")
new_player = PlayerCreate(
    name="Travis Hunter",
    position="Edge Rusher",
    school="Colorado",
    conference="Pac-12",
    recruiting_rating=9.7,
    recruiting_stars=5
)

try:
    player = create_player(new_player)
    print(f"✅ Created player: {player.name} (ID: {player.id})")
except Exception as e:
    print(f"❌ Error creating player: {e}")

# Example 2: Get all players
print("\n" + "=" * 50)
print("Fetching all players...")
try:
    all_players = get_all_players()
    print(f"✅ Found {len(all_players)} players")
    for player in all_players:
        print(f"  - {player.name} ({player.school})")
except Exception as e:
    print(f"❌ Error fetching players: {e}")

# Example 3: Get a specific player
print("\n" + "=" * 50)
print("Fetching a specific player...")
try:
    if all_players:
        player_id = all_players[0].id
        player = get_player(player_id)
        if player:
            print(f"✅ Found: {player.name} - {player.position}")
except Exception as e:
    print(f"❌ Error fetching player: {e}")

# Example 4: Get players by school
print("\n" + "=" * 50)
print("Fetching players from Colorado...")
try:
    colorado_players = get_players_by_school("Colorado")
    print(f"✅ Found {len(colorado_players)} players from Colorado")
    for player in colorado_players:
        print(f"  - {player.name}")
except Exception as e:
    print(f"❌ Error fetching players by school: {e}")

print("\n" + "=" * 50)
print("Done!")
