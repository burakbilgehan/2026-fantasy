from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import capture, health, league
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="2026-fantasy", lifespan=lifespan)
app.include_router(health.router)
app.include_router(league.router)
app.include_router(capture.router)
