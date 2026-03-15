import os
from pathlib import Path
from supabase import create_client
from dotenv import load_dotenv

# Load from the project root .env file
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_KEY = os.getenv("DATABASE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL or DATABASE_API_KEY environment variables are not set. Please check your .env file.")

client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_client():
    return client
