from create_tables import create_table_sql
from connection import get_client
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_KEY = os.getenv("DATABASE_API_KEY")

# Extract project ID from URL
project_id = SUPABASE_URL.split("https://")[1].split(".supabase.co")[0]

# Supabase Management API endpoint
MGMT_API_URL = f"https://api.supabase.com/v1/projects/{project_id}/api/sql"

# SQL to create the players table
sql = """
CREATE TABLE IF NOT EXISTS players (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  position TEXT,
  school TEXT,
  conference TEXT,
  recruiting_rating NUMERIC,
  recruiting_stars SMALLINT,
  created_at TIMESTAMP DEFAULT NOW()
);
"""

# Headers for the Management API
headers = {
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Send request to create table
payload = {"query": sql}

try:
    response = requests.post(MGMT_API_URL, json=payload, headers=headers)
    if response.status_code == 200:
        print("✅ Tables created successfully!")
    else:
        print(f"⚠️  Table creation response: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"❌ Failed to create table: {e}")
    print("\nNote: If this fails, create the table manually via Supabase Dashboard > SQL Editor")

