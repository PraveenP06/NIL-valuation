# NIL Valuation — Implementation Roadmap 2026

## Phase 0 — Social Scrape Completion + Baseline Re-calibration *(blocker)*

1. Wait for social scraper to finish (~3,962 players, ~7hr job)
2. Verify: query `social_media` for count of non-null `total_followers` — confirm it increased
3. Spot-check 10–20 newly-populated rows for plausible follower counts
4. Re-run calibration:
   ```
   python src/valuation/calibrate_model.py --season 2024
   ```
   - Watch: `social` mean in feature table should rise
   - Target: curated accuracy stays ≥ 82%

---

## Phase 1 — Model Accuracy: Mid/Low Tier *(highest-leverage model work)*

### 1.1 Profile-based guardrails (replaces manual label strategy)

**The mid/low tier label problem is unsolvable:** On3 paywalls everything below ~$1.5M and there is no public source for $200K–$800K deal data. Do not pursue manual curation — the data simply does not exist online.

**Correct approach:** The regression model already ranks players correctly relative to each other. The problem is absolute dollar calibration for the long tail. Fix this with deterministic profile-based guardrails in `calibrate_model.py` post-processing, derived from how collectives actually operate:

| Player Profile | Guardrail Range |
|---|---|
| G5 player, any role, no stats | $10K–$30K |
| G5 starter, decent stats, low social | $30K–$80K |
| G5 star, good stats, decent social | $80K–$200K |
| P4 backup / depth, no stats, no social | $50K–$100K |
| P4 backup with real stats but no social | $100K–$200K |
| P4 starter at lower P4 school (Big 12, ACC), avg stats | $150K–$350K |
| P4 starter at upper P4 school (SEC, Big Ten), avg stats | $250K–$500K |
| Non-skill (OL/DL/LB) P4 starter, good stats | $100K–$400K |

These are enforced as floor + cap bands keyed on `(conference_tier, has_stats, social_tier)`. The model's continuous score determines where within the band the player lands. This is intuitive and matches collective market reality without requiring any labeled data.

### 1.2 Recruit rankings integration

`pull_recruit_rankings.py` is complete. The `recruit_score` feature is already wired into the model (index 6 in `_feature_vector()`) but defaulting to 20.0 for most players.

Steps:
1. Run `python src/db/ingestion/pull_recruit_rankings.py`
2. Verify: `SELECT recruiting_stars, COUNT(*) FROM players GROUP BY recruiting_stars` — confirm 5-star/4-star distribution
3. Re-run calibration — recruit feature will now have real values
4. Spot-check: Arch Manning (Texas QB) should score near 100 recruit without over-inflating his prediction

**Note:** Transfer players retain their original recruiting stars (prestige follows the player), which is correct behavior.

### 1.3 Collective payout floor enforcement

Add minimum floors in `calibrate_model.py` post-processing alongside existing caps:
- G5 starter with stats: floor ~$30K–$50K
- P4 backup, no social: floor ~$50K–$80K
- P4 starter (non-QB, non-WR): floor ~$80K–$150K

---

## Phase 2 — API Completion

**Current state:** `src/api/main.py` running with three routers (players, valuations, stats). Endpoints functional but thin.

### 2.1 Endpoints to add

- `GET /api/players/{id}/valuation` — combined player + full score breakdown (perf, social, school, position, conference, class, recruit) — primary endpoint every frontend consumer needs
- `GET /api/valuations/top` — leaderboard with `position`, `conference`, `school` filters; fix PostgREST join-filter bug (Supabase foreign table filters don't always work — may need a DB view)
- `GET /api/school/{school}/top` — top N players by school with valuations
- `GET /api/compare?ids=1,2,3` — parallel valuation breakdowns for comparison view

### 2.2 Schema updates

`ValuationBase` Pydantic model and the `valuations` Supabase table are missing: `class_score`, `recruit_score`, `collective_score`. These are computed by `estimate_nil_value()` but not persisted. Add columns + update model before building frontend breakdown view.

### 2.3 Predictions → DB sync

After every calibration run, push `nil_predictions_calibrated.csv` into the `valuations` table (upsert script). This step is currently manual and undocumented — formalize it.

### 2.4 Response caching

Add TTL cache (e.g., `cachetools.TTLCache`) at the route level for leaderboard and school endpoints. Data only changes when calibration re-runs (~weekly).

### 2.5 Deployment

Deploy to Railway or Render. Set `DATABASE_URL`, `DATABASE_API_KEY`, `CFB_API_KEY` as env vars.

---

## Phase 3 — Frontend MVP (Next.js, separate repo)

**Stack:** Next.js 15 (App Router) + TypeScript + TailwindCSS + shadcn/ui. Deploy to Vercel.

**4 pages:**

| Page | Route | Key Content |
|---|---|---|
| Leaderboard | `/` | Top 200 players, sortable, filterable by position/conference/class year |
| Player Detail | `/players/[id]` | Hero with NIL value, 6-bar score breakdown, stats card, social card |
| School Page | `/school/[name]` | Top 25 players + school header |
| Search | `/search` | Free-text name search |

**Key differentiator to surface in UI:** "NIL valuations for all 15,000+ players, not just the top 500."

**Defer post-MVP:** comparison tool, historical charts, mobile app, auth, saved players.

---

## Phase 4 — Monetization Readiness *(post-MVP)*

Evaluate after live MVP and usage signals:

- **Collective intel:** conference-level analytics for schools
- **Agent dashboard:** portfolio view for agents managing 10–30 players
- **Brand matching:** find players by follower range, position, school

**Technical prerequisites:**
- Auth (NextAuth or Supabase Auth)
- Rate limiting on API (currently open CORS)
- Usage analytics (PostHog / Plausible)
- Stripe integration when free tier limit defined

---

## Dependency Map

```
Social scrape completes
        │
        ▼
Re-run calibration (Phase 0)
        │
        ├──► Add manual mid-tier labels (1.1) ──► Re-calibrate
        ├──► Run pull_recruit_rankings.py (1.2) ──► Re-calibrate
        └──► Add floor enforcement (1.3) ──► included in next calibration
                                                    │
                                                    ▼
                                       Update valuations table schema
                                       (add class_score, recruit_score, collective_score)
                                                    │
                                                    ▼
                                       Add missing API endpoints (Phase 2)
                                       + Deploy API to Railway
                                                    │
                                                    ▼
                                       Build Next.js frontend (Phase 3)
                                       + Deploy to Vercel
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scraper introduced bad Instagram matches | Medium | Medium | Spot-check 20 newly-populated rows before re-calibrating |
| `recruit_rankings` bulk update SQL fails on Supabase free tier | High | Medium | Replace bulk RPC with individual upserts as fallback |
| On3 blocks scraper | Medium | Low | Don't depend on live On3; 3,796-entry cache in `on3_rank_labels.json` is sufficient |
| PostgREST join-filter bug on valuations list | Medium | Medium | Test `/api/valuations?position=QB` before building frontend; use a DB view if needed |
| `nil_predictions_calibrated.csv` out of sync with `valuations` table | High | High | Create explicit upsert script + add to calibration runbook |

---

## Immediate Next Actions (ordered)

1. [ ] Wait for social scrape to finish, verify row count
2. [ ] Run `pull_recruit_rankings.py` to populate recruit data
3. [ ] Implement profile-based guardrail bands in `calibrate_model.py` post-processing
4. [ ] Re-run `calibrate_model.py --season 2024`
5. [ ] Upsert new predictions into `valuations` table
6. [ ] Add `class_score`, `recruit_score`, `collective_score` to `valuations` schema + `ValuationBase` model
7. [ ] Add missing API endpoints + fix join-filter bug
8. [ ] Deploy API to Railway
9. [ ] Initialize Next.js repo, build 4 MVP pages
10. [ ] Deploy frontend to Vercel
