"""Auto-trade control endpoints -- master switch, risk config, emergency
close-all. Every state change here is logged to the audit table."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.persistence import get_autotrade_audit
from app.risk import RiskConfig
from app.scheduler import scheduler_state

router = APIRouter(prefix="/autotrade", tags=["autotrade"])


class RiskConfigIn(BaseModel):
    risk_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_weekly_loss_pct: float | None = None
    max_concurrent_trades: int | None = None
    cooldown_minutes_after_loss: int | None = None
    min_grade: str | None = None
    min_backtest_sample: int | None = None
    min_backtest_winrate: float | None = None


@router.get("/status")
async def get_status():
    return {
        "auto_trade_enabled": scheduler_state.auto_trade_enabled,
        "dry_run": settings.dry_run,
        "broker_configured": scheduler_state.broker is not None,
        "kill_switch": scheduler_state.risk_state.kill_switch,
        "risk_config": scheduler_state.risk_config.__dict__,
        "open_trades": len(scheduler_state.risk_state.open_trades()),
        "last_scan_at": scheduler_state.last_scan_at.isoformat() if scheduler_state.last_scan_at else None,
    }


@router.post("/enable")
async def enable_auto_trade():
    if not scheduler_state.broker:
        raise HTTPException(400, "No MetaApi credentials configured -- set METAAPI_TOKEN and METAAPI_ACCOUNT_ID first.")
    scheduler_state.auto_trade_enabled = True
    return {"auto_trade_enabled": True, "dry_run": settings.dry_run}


@router.post("/disable")
async def disable_auto_trade():
    scheduler_state.auto_trade_enabled = False
    return {"auto_trade_enabled": False}


@router.post("/kill-switch")
async def engage_kill_switch():
    """Immediately stops all new auto-trades, independent of the master switch."""
    scheduler_state.risk_state.kill_switch = True
    return {"kill_switch": True}


@router.post("/kill-switch/release")
async def release_kill_switch():
    scheduler_state.risk_state.kill_switch = False
    return {"kill_switch": False}


@router.post("/close-all")
async def close_all_positions():
    """Emergency close-all, works regardless of auto-trade or dry-run state
    (though in dry-run it only logs what it would have closed)."""
    if not scheduler_state.broker:
        raise HTTPException(400, "No broker configured.")
    results = await scheduler_state.broker.close_all_positions()
    return {"results": [r.__dict__ for r in results]}


@router.put("/risk-config")
async def update_risk_config(cfg: RiskConfigIn):
    current = scheduler_state.risk_config
    for field, value in cfg.model_dump(exclude_none=True).items():
        setattr(current, field, value)
    return current.__dict__


@router.get("/audit-log")
async def audit_log(limit: int = 100):
    return {"entries": await get_autotrade_audit(limit)}
