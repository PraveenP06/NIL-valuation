from crud import create_performance_stats, get_stats_by_player, get_top_performers_by_season, get_all_players
from models import PerformanceStatsCreate

# Get the first player from database
players = get_all_players()
if not players:
    print("❌ No players in database! Add players first.")
    exit(1)

player = players[0]
print(f"Using player: {player.name} (ID: {player.id})")
print("=" * 50)

# Create sample performance stats for this player
sample_stats = PerformanceStatsCreate(
    player_id=player.id,
    season=2023,
    total_yards=3500.0,
    touchdowns=28,
    attempts=420,
    yards_per_game=268.0,
    usage_share=0.65,
    team_wins=12,
    efficiency_metric=0.88
)

try:
    stats = create_performance_stats(sample_stats)
    print(f"✅ Created performance stats! ID: {stats.id}")
    print(f"   Player: {stats.player_id}")
    print(f"   Season: {stats.season}")
    print(f"   Yards: {stats.total_yards}")
    print(f"   TDs: {stats.touchdowns}")
except Exception as e:
    print(f"❌ Error creating stats: {e}")

# Get all stats for this player
print("\n" + "=" * 50)
print(f"Getting all stats for {player.name}...")
try:
    player_stats = get_stats_by_player(player.id)
    print(f"✅ Found {len(player_stats)} stat records")
    for stat in player_stats:
        print(f"   Season {stat.season}: {stat.total_yards} yards, {stat.touchdowns} TDs")
except Exception as e:
    print(f"❌ Error: {e}")

# Get top performers
print("\n" + "=" * 50)
print("Getting top 5 performers by yards in 2023...")
try:
    top_performers = get_top_performers_by_season(2023, "total_yards", 5)
    print(f"✅ Found {len(top_performers)} top performers")
    for i, stat in enumerate(top_performers, 1):
        print(f"   {i}. Player {stat.player_id}: {stat.total_yards} yards")
except Exception as e:
    print(f"❌ Error: {e}")

