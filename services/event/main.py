"""
Event Worker — FastAPI entry point
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, close_db
from routers.public import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EVENT_CODE = os.getenv("EVENT_CODE", "UNKNOWN")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting event worker for event: %s", EVENT_CODE)
    await init_db()
    logger.info("✅ SQLite initialised at %s", os.path.join(os.getenv("EFS_MOUNT", "/data"), "event.db"))
    yield
    await close_db()
    logger.info("Event worker shut down: %s", EVENT_CODE)


app = FastAPI(
    title=f"SnapEvent Worker [{EVENT_CODE}]",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENV", "dev") == "dev" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
