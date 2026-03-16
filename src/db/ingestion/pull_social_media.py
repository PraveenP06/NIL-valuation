import os
import sys
import csv
from datetime import datetime, timezone
from dotenv import load_dotenv
from tqdm import tqdm
# THIS FILE INGESTS PLAYER SOCIAL MEDIA DATA FROM A CSV INTO THE DATABASE
# CSV format (see social_media_template.csv for reference):
#   player_name, school, instagram_followers, twitter_followers, tiktok_followers,
#   youtube_subscribers, engagement_rate, avg_post_likes, follower_growth_30d,
#   verified_instagram, verified_twitter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.crud import upsert_social_media
from db.models import SocialMediaCreate
from db.connection import get_client

load_dotenv()

REQUIRED_COLUMNS = {"player_name", "school"}


def _int(val):
    try:
        return int(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _float(val):
    try:
        return float(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _bool(val):
    if val in (None, ""):
        return None
    return str(val).strip().lower() in ("true", "1", "yes")


def resolve_player_id(client, name: str, school: str) -> int | None:
    """Look up player_id by name + school (exact match)."""
    resp = (
        client.table("players")
        .select("id")
        .eq("name", name)
        .eq("school", school)
        .limit(1)
        .execute()
    )
    if resp.data:
        return resp.data[0]["id"]
    # fallback: name only if unique
    resp2 = client.table("players").select("id").eq("name", name).execute()
    if resp2.data and len(resp2.data) == 1:
        return resp2.data[0]["id"]
    return None


def ingest_csv(filepath: str):
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    added = skipped = failed = 0

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - cols
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        rows = list(reader)

    print(f"Processing {len(rows)} rows from {filepath}\n")

    for row in tqdm(rows, desc="Upserting social media", unit="player"):
        name = row.get("player_name", "").strip()
        school = row.get("school", "").strip()

        player_id = resolve_player_id(client, name, school)
        if player_id is None:
            print(f"  ✗ Could not match: {name} ({school})")
            failed += 1
            continue

        ig = _int(row.get("instagram_followers"))
        tw = _int(row.get("twitter_followers"))
        total = sum(v for v in [ig, tw] if v is not None) or None

        social = SocialMediaCreate(
            player_id=player_id,
            instagram_followers=ig,
            twitter_followers=tw,
            total_followers=total,
            engagement_rate=_float(row.get("engagement_rate")),
            avg_post_likes=_int(row.get("avg_post_likes")),
            verified_instagram=_bool(row.get("verified_instagram")),
            verified_twitter=_bool(row.get("verified_twitter")),
            last_updated=now,
        )

        try:
            upsert_social_media(social)
            added += 1
        except Exception as e:
            print(f"  ✗ Failed upsert for {name}: {e}")
            failed += 1

    print(f"\n✅ Done!")
    print(f"  ✓ Upserted: {added}")
    print(f"  ↷ Skipped:  {skipped}")
    print(f"  ✗ Failed:   {failed}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest social media data from CSV")
    parser.add_argument("--file", required=True, help="Path to input CSV file")
    args = parser.parse_args()
    ingest_csv(args.file)
