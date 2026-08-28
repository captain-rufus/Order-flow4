"""Signal + Scanner endpoints -- mirrors the browser tool's scan/scanner
behavior, plus a cached-results endpoint that surfaces what the background
scheduler has already found without triggering a new scan."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.binance import load_crypto_data
from app.data.deriv import deriv_client
from app.models import Market
from app.scheduler import scan_pair, scheduler_state

router = APIRouter(prefix="/signals", tags=["signals"])


class SignalOut(BaseModel):
    strategy: str
    direction: str
    confidence: float
    grade: str
    grade_label: str
    entry: float | None
    stop: float | None
    tp1: float | None
    tp2: float | None
    tp3: float | None
    rr: float | None
    reason: str
    is_pending: bool
    pending_direction: str | None
    is_error: bool
    confluence_score: float
    probability_score: float
    risk_score: float


def _to_out(s) -> SignalOut:
    return SignalOut(
        strategy=s.strategy, direction=s.direction.value, confidence=s.confidence,
        grade=s.grade, grade_label=s.grade_label, entry=s.entry, stop=s.stop,
        tp1=s.tp1, tp2=s.tp2, tp3=s.tp3, rr=s.rr, reason=s.reason,
        is_pending=s.is_pending, pending_direction=s.pending_direction, is_error=s.is_error,
        confluence_score=s.confluence_score, probability_score=s.probability_score, risk_score=s.risk_score,
    )


@router.get("/synthetic/symbols")
async def list_synthetic_symbols():
    symbols = deriv_client.known_symbols or await deriv_client.load_symbol_list()
    return {"symbols": symbols}


@router.get("/{market}/{pair}")
async def get_signals(market: str, pair: str):
    """Triggers a fresh, on-demand scan for one pair right now. Includes the
    raw backtest numbers alongside the signals so a client can show its own
    per-strategy win/loss badges instead of only the folded grade."""
    if market not in (Market.CRYPTO.value, Market.SYNTHETIC.value):
        raise HTTPException(400, "market must be 'crypto' or 'synthetic'")
    try:
        signals = await scan_pair(market, pair)
    except Exception as err:
        raise HTTPException(502, f"Couldn't fetch real data for {pair}: {err}")
    backtests = scheduler_state.latest_backtests.get(f"{market}:{pair}", {})
    return {
        "pair": pair, "market": market,
        "signals": [_to_out(s).model_dump() for s in signals],
        "backtests": backtests,
    }


@router.get("/{market}")
async def get_cached_market_signals(market: str):
    """Returns whatever the background scheduler has ALREADY found for every
    pair in this market, without triggering a new scan -- this is the real
    'continuous scanning' dashboard data, reflecting up to
    settings.scan_interval_seconds of staleness rather than being instant."""
    if market not in (Market.CRYPTO.value, Market.SYNTHETIC.value):
        raise HTTPException(400, "market must be 'crypto' or 'synthetic'")

    results = {}
    prefix = f"{market}:"
    for key, signals in scheduler_state.latest_signals.items():
        if key.startswith(prefix):
            pair = key[len(prefix):]
            results[pair] = [_to_out(s).model_dump() for s in signals]

    return {
        "market": market,
        "pairs": results,
        "last_scan_at": scheduler_state.last_scan_at.isoformat() if scheduler_state.last_scan_at else None,
        "is_stale": scheduler_state.last_scan_at is None,
    }

