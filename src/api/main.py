import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.valuations import router as valuations_router
from api.routes.players import router as players_router
from api.routes.stats import router as stats_router

app = FastAPI(title="NIL Valuation API", version="1.0.0")

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
