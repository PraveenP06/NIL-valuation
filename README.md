# CFB NIL Valuation

Model-driven NIL valuations for 7,700+ college football players. Built on performance stats, social media following, school prestige, recruiting pedigree, collective strength, and class year.

**Spearman ρ = 0.644** on labeled ground truth · **7,738** players valued for the 2025 season · top prediction **$5.5M** (Arch Manning)

---

## Architecture

```
src/
├── db/
│   ├── connection.py          # Supabase client singleton
│   ├── models.py              # Pydantic models
│   ├── crud.py                # DB operations
│   └── ingestion/             # Data pipeline scripts
│       ├── pull_cfb_players.py
│       ├── pull_performance_stats.py
│       ├── pull_social_media_free.py
│       ├── pull_recruit_rankings.py
│       ├── upsert_valuations.py
│       └── upsert_public_valuations.py
├── valuation/
│   ├── model.py               # 6-factor scoring (0-100 each)
│   └── calibrate_model.py     # Ridge/Huber regression calibration
└── api/
    ├── main.py                # FastAPI app + CORS + rate limiting
    ├── limiter.py             # slowapi limiter instance
    └── routes/
        ├── valuations.py      # GET /api/valuations
        ├── players.py         # GET /api/players/search, /api/players/{id}/valuation
        ├── school.py          # GET /api/school/{name}/top
        ├── filters.py         # GET /api/filters/meta
        └── stats.py           # GET /api/stats

frontend/
├── app/                       # Next.js 15 App Router pages
│   ├── page.tsx               # Leaderboard
│   ├── search/page.tsx        # Player search
│   ├── players/[id]/page.tsx  # Player detail
│   └── school/[name]/page.tsx # School breakdown
├── components/
│   ├── leaderboard/           # FilterBar, PlayerTable, LeaderboardContainer
│   ├── player/                # PlayerHero, ScoreBreakdownChart, PublicValuationsTable
│   ├── search/                # SearchContainer, SearchResultCard
│   ├── shared/                # NilValueBadge, ComparisonIndicator, StatCard, PositionBadge
│   └── ui/                    # shadcn/ui primitives (Button, Select, Progress, etc.)
└── lib/
    ├── api.ts                 # Typed fetch wrappers for all endpoints
    ├── types.ts               # TypeScript types
    ├── format.ts              # formatNilValue, classYearLabel, etc.
    └── query-provider.tsx     # TanStack Query provider
```

---

## Local Setup

### Prerequisites
- Python 3.11+
- Node.js 20+
- A [Supabase](https://supabase.com) project
- A [College Football Data API](https://collegefootballdata.com) key

### Backend

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env at project root with:
# DATABASE_URL=https://<id>.supabase.co
# DATABASE_API_KEY=<anon-key>
# CFB_API_KEY=<cfb-key>

cd src
uvicorn api.main:app --reload --port 8000
# Docs at http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install
npm run dev
# http://localhost:3000
```

---

## Data Pipeline

Run all scripts from the **project root**:

```bash
python src/db/ingestion/pull_cfb_players.py --year 2025
python src/db/ingestion/pull_performance_stats.py --year 2025
python src/db/ingestion/pull_social_media_free.py
python src/db/ingestion/pull_recruit_rankings.py
python src/db/ingestion/upsert_public_valuations.py
python src/valuation/calibrate_model.py --season 2025
python src/db/ingestion/upsert_valuations.py --season 2025
```

---

## API Endpoints

| Route | Description | Rate Limit |
|---|---|---|
| `GET /api/valuations` | Paginated leaderboard (season, position, conference, class_year filters) | 60/min |
| `GET /api/valuations/top` | Top N valuations | 60/min |
| `GET /api/players/search?q=` | Player name search | 30/min |
| `GET /api/players/{id}/valuation` | Full player breakdown + public deals | 60/min |
| `GET /api/school/{name}/top` | Top players at a school | 60/min |
| `GET /api/filters/meta` | Positions, conferences for dropdowns (cached) | 30/min |
| `GET /api/stats` | DB-wide stats for a season | 30/min |
| `GET /health` | Health check | — |

---

## Model

**6 scoring factors (0–100 each):**

| Factor | Weight | Signal |
|---|---|---|
| Performance | 20% | Yards, TDs, efficiency, team wins |
| Social | 20% | Instagram followers + engagement |
| School Prestige | 15% | Program tier (Alabama=95, G5=50) |
| Recruit Pedigree | 20% | Star rating × class-year decay |
| Class Year | 5% | FR=50, SO=70, JR=90, SR=75 |
| Collective Strength | — | School NIL budget (Texas=100, G5=10) |

Plus position multiplier (QB=1.5×) and conference multiplier (SEC=1.3×).

Ridge/Huber regression in log-space on a 13-feature vector. Trained on 48 curated labels ($700K–$6.8M) + rank-derived soft labels.

**Accuracy (out-of-sample, n=81):** Spearman ρ=0.644 · within-20%=32.1% · median error=33.3%

---

## Deployment

- **API:** Vercel — create a project with the repository root as its Root Directory. Set
  `DATABASE_URL`, `DATABASE_API_KEY`, and `FRONTEND_ORIGIN` in its environment variables.
- **Frontend:** Vercel — create a second project from the same repository with `frontend/`
  as its Root Directory. Set `NEXT_PUBLIC_API_URL` to the deployed API URL before building.

The root `requirements.txt` contains only API runtime packages so the Vercel Function stays
small. For local ingestion and model-training scripts, also install
`requirements-ingestion.txt`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Uvicorn, slowapi |
| Database | Supabase (PostgreSQL) |
| ML | scikit-learn, scipy, numpy, pandas |
| Frontend | Next.js 15, React 19, TypeScript |
| Styling | Tailwind CSS, Shadcn/ui |
