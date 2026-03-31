# Implementation Plan: NIL Valuation Frontend

## What We're Building

A public, read-only Next.js 15 frontend where anyone can:
1. Browse/search ~15,000 college football players
2. View our model's NIL valuation + full score breakdown
3. See a green/red comparison indicator when a public NIL figure exists for that player

---

## Pages

### `/` — Leaderboard
- Dashboard stat cards (total players, total valuations, top NIL value)
- Filterable table: position, conference, class year, season
- Columns: Rank, Name, Position, School, Conference, NIL Value, Public Value (if known), Indicator
- Click row → Player Detail

### `/players/[id]` — Player Detail
- Hero: name, position, school, conference, class year, large NIL dollar value
- **Public comparison badge** (only shown when public value exists):
  - 🟢 Green: our value >= public value
  - 🔴 Red: our value < public value
- Score breakdown: 6 horizontal bars (perf, social, school, class, recruit, collective, each 0–100)
- Multiplier pills: position, conference

### `/school/[name]` — School Page
- Top 25 players at a school sorted by NIL value
- Same comparison indicator in each row

### `/search` — Search
- Debounced real-time name search (300ms, min 2 chars)
- Result cards → click to player detail

---

## Public Valuation Storage Decision

**Recommendation: Separate `public_valuations` table** (not a column on `valuations`)

Reasons:
- Already have 3,899 entries across `on3_rank_labels.json` and `nil_websearch.json` with source tracking
- Multiple sources/seasons per player handled cleanly
- Keeps model output (`valuations`) separate from external data

**Table schema:**
```sql
public_valuations (
  id           SERIAL PRIMARY KEY,
  player_id    INTEGER REFERENCES players(id),
  season       INTEGER NOT NULL,
  nil_value    NUMERIC NOT NULL,
  source       TEXT NOT NULL,  -- 'on3_rank_estimate', 'forbes_reported', etc.
  scraped_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(player_id, season, source)
)
```

**New API endpoint needed:**
- Extend `GET /api/players/{player_id}/valuation` to include `public_valuations: []` array
- Extend `GET /api/valuations` leaderboard to include `public_nil_value` column (left join max per player)

---

## Implementation Phases

### Phase 1: Backend Prep (Python)
1. Create `public_valuations` table in Supabase
2. Write `src/db/ingestion/upsert_public_valuations.py` (reads JSON files, matches player_id, upserts)
3. Extend leaderboard API to include public value per player
4. Extend player valuation endpoint to include public values array

### Phase 2: Frontend Scaffold
1. `npx create-next-app@latest frontend --typescript --tailwind --app`
2. Install shadcn/ui, React Query, recharts
3. `lib/types.ts` + `lib/api.ts` + `lib/format.ts`
4. React Query provider + custom hooks
5. Root layout (Navbar + Footer)

### Phase 3: Core Pages
1. Leaderboard (`/`) — filters, pagination, comparison indicators
2. Player Detail (`/players/[id]`) — hero, score bars, comparison badge
3. Search (`/search`) — debounced input, result cards
4. School (`/school/[name]`) — top players table

### Phase 4: Polish + Deploy
1. Loading skeletons, error boundaries, 404 pages
2. SEO metadata + Open Graph
3. Deploy FastAPI to Render
4. Deploy frontend to Vercel
5. Tighten CORS from `*` to Vercel domain

---

## Component List

| Component | Purpose |
|---|---|
| `PlayerTable` | Reusable ranked table (leaderboard + school pages) |
| `PlayerRow` | Single row with comparison indicator |
| `ComparisonIndicator` | Green/red dot+value — hidden when no public data |
| `NilValueBadge` | Formatted dollar value ($1.2M, $350K) |
| `ScoreBreakdownChart` | 6 horizontal score bars (0–100) |
| `MultiplierPill` | "QB 1.5x", "SEC 1.3x" pills |
| `StatCard` | Dashboard number + label card |
| `FilterBar` | Position/conference/class year/season dropdowns |
| `SearchInput` | Debounced text input |
| `PlayerHero` | Large header card on player detail |
| `LoadingSkeleton` | Shimmer placeholders |
| `EmptyState` | No-results placeholder |

---

## Risks

| Risk | Mitigation |
|---|---|
| On3 JSON → player_id matching misses entries | Log unmatched entries, start with exact (name, school) match, report match rate |
| Leaderboard left-join on public_valuations is slow | Do two queries in API route instead of view join |
| School names with special chars break routing | `encodeURIComponent` / `decodeURIComponent` consistently |
| API rate limits too low for real traffic | Increase after launch; frontend caching reduces calls |

---

## Success Criteria

- [ ] Leaderboard loads with top players and NIL values
- [ ] Filters work (position, conference, class year)
- [ ] Player detail shows full score breakdown
- [ ] Search finds any of ~15,000 players by name
- [ ] School page shows top 25 players
- [ ] Green/red indicator shown when public value exists, hidden when not
- [ ] All pages mobile-responsive
- [ ] Deployed to Vercel, API on Render
