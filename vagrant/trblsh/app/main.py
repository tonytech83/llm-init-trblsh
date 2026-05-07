from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)

# Run with: uvicorn app.main:app --host 0.0.0.0 --port 8080
