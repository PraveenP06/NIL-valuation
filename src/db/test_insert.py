from crud import create_player
from models import PlayerCreate

new_player = PlayerCreate(
    name="Test QB",
    position="QB",
    school="Georgia Tech",
    conference="ACC",
    recruiting_rating=0.89,
    recruiting_stars=4
)

player = create_player(new_player)
print(f"Inserted! Player ID: {player.id}")

