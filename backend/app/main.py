import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import capture, draft, health, knowledge, league, players, sync, valuation
from app.db import init_db
from app.jobs import refresh


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    stop = threading.Event()
    if refresh.enabled():
        refresh.start_loop(stop)
    yield
    stop.set()


app = FastAPI(title="2026-fantasy", lifespan=lifespan)
app.include_router(health.router)
app.include_router(league.router)
app.include_router(capture.router)
app.include_router(players.router)
app.include_router(draft.router)
app.include_router(sync.router)
app.include_router(knowledge.router)
app.include_router(valuation.router)
