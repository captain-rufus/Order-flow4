"""
ORDERFLOW backend -- real, always-on version of the browser tool's signal
engine, with optional (off-by-default) auto-trading via MetaApi.

Run: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.persistence import init_db
from app.routes import autotrade, journal, signals
from app.scheduler import scheduler_loop, scheduler_state, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_HTML_PATH = os.path.join(STATIC_DIR, "index.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("DRY_RUN=%s  AUTO_TRADE_ENABLED=%s  broker_configured=%s",
                settings.dry_run, settings.auto_trade_master_switch, scheduler_state.broker is not None)
    task = asyncio.create_task(scheduler_loop())
    yield
    stop_scheduler()
    task.cancel()


app = FastAPI(title="ORDERFLOW Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.include_router(signals.router)
app.include_router(autotrade.router)
app.include_router(journal.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "dry_run": settings.dry_run,
        "auto_trade_enabled": scheduler_state.auto_trade_enabled,
        "last_scan_at": scheduler_state.last_scan_at.isoformat() if scheduler_state.last_scan_at else None,
    }


@app.get("/")
async def serve_frontend():
    """Serves the same orderflow.html frontend tool, directly from this
    backend. Because it's then loaded from the backend's own origin, the
    frontend's auto-detect logic finds this backend automatically -- no
    manually pasting a URL into Settings. Opening the standalone
    orderflow.html file elsewhere (a Claude artifact, a static host, your
    local disk) still works exactly as before, just without that
    auto-connect convenience."""
    if not os.path.exists(INDEX_HTML_PATH):
        return {"error": "Frontend not bundled with this deployment -- app/static/index.html is missing."}
    return FileResponse(INDEX_HTML_PATH)
