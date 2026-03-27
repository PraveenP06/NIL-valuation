# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical Rules

- **NEVER commit anything unless explicitly asked.** Do not run `git commit` under any circumstance unless the user directly says to commit.
- **Always ask for confirmation before moving to the next step.** After completing any task or phase, stop and wait for approval before continuing.

## Environment Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Required `.env` at project root:
```
DATABASE_URL=https://<project-id>.supabase.co
DATABASE_API_KEY=<supabase-anon-key>
CFB_API_KEY=<collegefootballdata.com-key>
```

## Running Scripts

All scripts must be run from the **project root** (not from within `src/`), because they manipulate `sys.path` relative to their file location.

```bash
# Ingest player rosters from CFB API
python src/db/ingestion/pull_cfb_players.py --year 2024

# Ingest performance stats
python src/db/ingestion/pull_performance_stats.py --year 2023
python src/db/ingestion/pull_performance_stats.py --year 2023 --max-rows 100  # debug cap

# Run ad-hoc DB queries
python src/db/test_crud.py
python src/db/test_performance_stats.py
```

## Architecture

### Database Layer (`src/db/`)
- `connection.py` — creates a single Supabase client via `get_client()`. Always use `get_client()`, not a direct `supabase` import.
- `models.py` — Pydantic models. Pattern is `Base → Create → Full` (full adds `id` + `created_at`).
- `crud.py` — all DB operations. Imports `connection` and `models` using bare names (no `src.db` prefix) because it uses `sys.path.insert`.
- `ingestion/` — standalone scripts that pull from the CFB API and write to Supabase.

### Import Pattern (Critical)
Scripts inside `src/db/` do `sys.path.insert(0, ...)` to add `src/` to the path, then import as `from db.crud import ...`. Scripts inside `src/db/ingestion/` add `src/` two levels up and also import as `from db.crud import ...`. Do not use `from src.db.xxx import` — it will break.

### Supabase Tables
| Table | Rows (approx) | Key fields |
|---|---|---|
| `players` | ~15,000 | `id`, `name`, `school`, `conference`, `position`, `season` |
| `performance_stats` | ~3,100 | `player_id` (FK), `season`, `total_yards`, `touchdowns`, `efficiency_metric` |

`performance_stats` has a unique constraint on `(player_id, season)` — use `upsert` with `on_conflict="player_id,season"` when inserting stats.

Player matching in ingestion uses `normalize_player_name()` (strips suffixes like Jr/Sr/III) + `normalize_text()` (lowercases, removes punctuation). Primary match is `(name, school)`, fallback is unique name-only.

### Planned Modules (not yet built)
- `src/valuation/model.py` — NIL scoring engine
- `src/api/` — FastAPI routes
- Frontend: Next.js (separate repo TBD)

## Valuation Formula (Phase 3 target)

```python
NIL_VALUE = (
    perf_score * 0.30 +
    social_score * 0.25 +
    school_score * 0.20 +
    position_multiplier * 0.15 +
    conference_multiplier * 0.10
) * BASE_VALUE
```

Position multipliers: QB=1.5x, WR=1.2x, TE=1.1x, RB=1.0x, defense<1.0x
Conference multipliers: SEC=1.3x, Big Ten=1.2x, ACC=1.0x, Big 12=0.9x
