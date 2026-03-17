# NIL Valuation Project - Complete Roadmap

## PHASE 1: Data Foundation (COMPLETED ✅)
- [x] Set up Supabase database
- [x] Create players table with ~15,000 Power 4 roster records
- [x] Create performance_stats table with ~3,100 player records
- [x] Build CRUD operations for data management
- [x] Set up data ingestion pipelines

## PHASE 2: Enhanced Data Collection (MOSTLY DONE ✅)
### 2.1 Social Media Metrics
- [x] Create social_media table (player_id, instagram_followers, twitter_followers, total_followers, engagement_rate, avg_post_likes, verified_instagram, verified_twitter)
- [x] Build Instagram ingestion script (pull_social_media.py, pull_social_media_apify.py)
- [x] Create CRUD functions for social media data
- [ ] ~~Twitter API integration~~ — deferred, Instagram-only for MVP
- [ ] ~~TikTok API integration~~ — deferred, possibly added later

### 2.2 Team/School Metrics
- [ ] Create team_stats table (wins, losses, ranking, tv_appearances, recruiting_class_rank)
- [ ] Ingest team data from CFB API
- [ ] Link players to team performance data

### 2.3 Historical NIL Data
- [ ] Create nil_market_data table (reported_nil_value, deal_count, major deals)
- [ ] Research and manually add historical NIL values (ESPN, Opendorse, media reports)
- [ ] Create nil_history CRUD operations

## PHASE 3: Valuation Model (COMPLETED ✅)
### 3.1 Define Valuation Factors & Weights
```python
VALUATION_FACTORS = {
    "performance": 0.30,        # Yards, TDs, efficiency
    "social_media": 0.25,       # Followers, engagement
    "school_brand": 0.20,       # School ranking, prestige
    "position": 0.15,           # QB > RB > WR > Defense
    "conference": 0.10          # SEC > Big Ten > ACC > Big 12
}
```

### 3.2 Build Valuation Engine
- [x] `calculate_performance_score()` — normalizes stats (yards, TDs, efficiency, yards/game, team wins)
- [x] `calculate_social_score()` — log-scale follower normalization + engagement/verification bonuses
- [x] `calculate_school_score()` — tiered school prestige (Tier 1: 95, Tier 2: 75, fallback by conference)
- [x] `get_position_multiplier()` — QB=1.5x down to K/P=0.7x
- [x] `get_conference_multiplier()` — SEC=1.3x down to 0.8x default
- [x] `estimate_nil_value()` — full weighted composite formula
- [x] `valuations` table + CRUD (upsert_valuation, get_valuation, get_top_valuations)
- [x] Batch valuation script (run_valuation.py)

### 3.3 Valuation Formula
```
NIL_VALUE = (
    (perf_score * 0.30) +
    (social_score * 0.25) +
    (school_score * 0.20) +
    (position_score * 0.15) +
    (conference_score * 0.10)
) * BASE_VALUE
```

## PHASE 4: API & Backend (Expose to Users)
### 4.1 Create REST API Endpoints
- [ ] `/api/players` — List all players
- [ ] `/api/players/{id}` — Get player details
- [ ] `/api/players/{id}/valuation` — Get player's NIL valuation
- [ ] `/api/top-valuations` — Top 10/50/100 valued players
- [ ] `/api/compare` — Compare 2+ players
- [ ] `/api/school/{school}` — Top players by school
- [ ] `/api/position/{position}` — Top players by position
- [ ] `/api/search` — Search players by name/school

### 4.2 Build with FastAPI
- [ ] Install FastAPI, uvicorn
- [ ] Create src/api/ directory with route files
- [ ] Add error handling & validation
- [ ] Create API documentation (auto-generated via FastAPI)

## PHASE 5: Frontend (Visualization)
### 5.1 Web Dashboard
- [ ] Build with Next.js
- [ ] Player search/filter page
- [ ] Player detail page with valuation breakdown
- [ ] Leaderboard/ranking page
- [ ] Comparison tool (side-by-side)
- [ ] School/conference breakdown

### 5.2 Data Visualization
- [ ] Charts showing valuation factors breakdown
- [ ] Performance trends over time
- [ ] Social media growth trends
- [ ] School comparisons

## PHASE 6: Advanced Features
### 6.1 Analytics & Insights
- [ ] Identify undervalued players
- [ ] Track valuation changes over time
- [ ] Predict future valuations (ML model)
- [ ] Market trends report

### 6.2 Machine Learning (Optional — post-MVP)
- [ ] Train model on historical NIL data
- [ ] Predict future NIL values
- [ ] Identify emerging talent

### 6.3 Notifications
- [ ] Alert when players' valuations spike
- [ ] Track favorite players
- [ ] Compare to benchmarks

## PHASE 7: Deployment & Scaling
- [ ] Deploy API to cloud (Railway or Render recommended)
- [ ] Deploy frontend (Vercel)
- [ ] Set up CI/CD pipeline
- [ ] Database backups & monitoring
- [ ] Performance optimization

---

## MVP PLAN (Instagram-only social data)
Goal: get a working valuation model with real outputs before expanding data sources.

1. ✅ Performance stats ingested (2023 season)
2. ✅ Instagram followers ingested via Apify
3. ✅ Valuation model built and batch script working
4. **Next:** Build FastAPI layer (Phase 4) to expose valuations via endpoints
5. **Then:** Simple frontend leaderboard (Phase 5)
6. **Later:** Add Twitter, TikTok, team stats, historical NIL data

## Current Tech Stack
- Database: Supabase (PostgreSQL)
- Backend: Python + FastAPI (ready to build)
- Data Ingestion: CFB API, Apify (Instagram)
- Valuation: src/valuation/model.py
- Frontend: Next.js (to be built)
