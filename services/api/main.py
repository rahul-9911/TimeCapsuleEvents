"""
SnapEvent — FastAPI entry point + Lambda handler (Mangum)
Single app that handles all routes: auth, events, codes, participant photos.
"""
import os
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

from routers.auth import router as auth_router
from routers.events import router as events_router
from routers.codes import router as codes_router
from routers.participant import router as participant_router

# ── Logging ───────────────────────────────────────────────────────────────────
log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SnapEvent API",
    docs_url="/docs" if os.getenv("ENV", "dev") == "dev" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/auth")
app.include_router(events_router, prefix="/api/events")
app.include_router(codes_router, prefix="/api/events")
app.include_router(participant_router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "snapevent-api"}


# ── Frontend static files ─────────────────────────────────────────────────────
FRONTEND_DIR = os.getenv("FRONTEND_DIR", "/frontend")

if os.path.exists(FRONTEND_DIR):
    # Serve CSS/JS/images as static files
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(f"{FRONTEND_DIR}/login.html")

    # Catch-all for HTML pages
    @app.get("/{page}.html")
    async def serve_page(page: str):
        path = f"{FRONTEND_DIR}/{page}.html"
        if os.path.exists(path):
            return FileResponse(path)
        raise HTTPException(404, "Page not found")


# ── Lambda Handler ────────────────────────────────────────────────────────────
# Mangum translates API Gateway HTTP API events → ASGI requests for FastAPI
handler = Mangum(app, lifespan="off")
