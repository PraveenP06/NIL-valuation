import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.routes.valuations import router as valuations_router
from api.routes.players import router as players_router
from api.routes.stats import router as stats_router

# Rate limiter: keyed by client IP.
# Default limits per route are set in each router using @limiter.limit().
# Override globally here if needed.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/hour"])

app = FastAPI(title="NIL Valuation API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(valuations_router)
app.include_router(players_router)
app.include_router(stats_router)


@app.get("/health")
def health():
    return {"status": "ok"}
