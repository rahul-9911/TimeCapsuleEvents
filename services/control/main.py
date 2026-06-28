"""
Control Plane — FastAPI entry point
"""
import os
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import init_db, close_pool
from routers.auth import router as auth_router
from routers.events import router as events_router
from routers.codes import router as codes_router
from routers.participant import router as participant_router
from middleware import get_current_organiser
from db import get_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("✅ Database initialised")
    yield
    await close_pool()


app = FastAPI(title="SnapEvent Control Plane", lifespan=lifespan)

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
    return {"status": "ok", "service": "control-plane"}


# ── Proxy: /e/{code}/* → event container ──────────────────────────────────────
@app.api_route(
    "/e/{code}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
@app.api_route(
    "/e/{code}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_to_event(code: str, request: Request, path: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT internal_url, status FROM event_registry WHERE event_code = $1",
            code.upper(),
        )

    if not row:
        raise HTTPException(404, f"Event '{code}' not found")
    if row["status"] != "RUNNING":
        raise HTTPException(503, f"Event is {row['status']} — please wait or contact the organiser")
    if not row["internal_url"]:
        raise HTTPException(503, "Event container starting up — please try again in a few seconds")

    target_base = row["internal_url"].rstrip("/")
    target_path = f"/e/{code.upper()}" + (f"/{path}" if path else "")
    target_url = target_base + target_path

    # Forward headers (strip hop-by-hop)
    hop_by_hop = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
                  "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop}

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            rp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
                follow_redirects=False,
            )
    except httpx.ConnectError:
        raise HTTPException(503, "Event container unreachable — it may be starting up")
    except httpx.TimeoutException:
        raise HTTPException(504, "Event container timed out")

    # Strip hop-by-hop from response too
    resp_headers = {k: v for k, v in rp.headers.items() if k.lower() not in hop_by_hop}
    return Response(
        content=rp.content,
        status_code=rp.status_code,
        headers=resp_headers,
        media_type=rp.headers.get("content-type"),
    )


# ── Frontend static files ─────────────────────────────────────────────────────
FRONTEND_DIR = "/frontend"
if os.path.exists(FRONTEND_DIR):
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
