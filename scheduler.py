"""
Background scan loop -- this is what makes signals keep running whether or
not anyone has a browser open, unlike the client-side version which stops
the moment the tab is backgrounded. Runs every settings.scan_interval_seconds,
scans every enabled pair, and (if auto-trading is on) routes qualifying
signals through the risk gate and, if DRY_RUN is off, the real broker.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from app.alerts import format_autotrade_alert, format_signal_alert, notify
from app.backtest import run_all_backtests
from app.broker.metaapi_adapter import MetaApiAdapter
from app.config import settings
from app.data.binance import load_crypto_data
from app.data.deriv import deriv_client
from app.grading import apply_backtest_to_grading, compute_scores
from app.models import Direction, Market
from app.persistence import add_account_snapshot, add_journal_entry, log_autotrade_decision
from app.risk import RiskConfig, RiskState, calculate_position_size, can_auto_execute
from app.strategies.registry import run_engine

logger = logging.getLogger(__name__)


class SchedulerState:
    """Shared, in-memory state the API routes can read/toggle. In a real
    multi-process deployment this would live in Redis/the DB instead --
    kept simple here since this is a single-process reference server."""

    def __init__(self):
        self.running = False
        self.auto_trade_enabled = settings.auto_trade_master_switch
        self.risk_config = RiskConfig()
        self.risk_state = RiskState()
        self.latest_signals: dict[str, list] = {}   # "market:pair" -> list[Signal]
        self.latest_backtests: dict[str, dict] = {}  # "market:pair" -> backtest dict
        self.last_scan_at: datetime | None = None
        self.broker: MetaApiAdapter | None = None
        if settings.metaapi_token and settings.metaapi_account_id:
            self.broker = MetaApiAdapter(settings.metaapi_token, settings.metaapi_account_id,
                                          dry_run=settings.dry_run)


scheduler_state = SchedulerState()


async def scan_pair(market: str, pair: str) -> list:
    if market == Market.CRYPTO.value:
        candles = await load_crypto_data(pair)
    else:
        candles = await deriv_client.load_all_timeframes(pair)

    signals = run_engine(candles)
    for s in signals:
        compute_scores(s)
    backtests = run_all_backtests(candles)
    apply_backtest_to_grading(signals, backtests)

    key = f"{market}:{pair}"
    scheduler_state.latest_signals[key] = signals
    scheduler_state.latest_backtests[key] = backtests
    return signals


async def maybe_auto_execute(market: str, pair: str, signals: list) -> None:
    if not scheduler_state.auto_trade_enabled:
        return
    if not scheduler_state.broker:
        logger.warning("Auto-trade is ON but no MetaApi credentials are configured -- nothing to execute against.")
        return

    actionable = [s for s in signals if s.direction != Direction.WAIT and not s.is_error]
    if not actionable:
        return
    best = max(actionable, key=lambda s: s.confidence)

    try:
        account = await scheduler_state.broker.get_account_info()
    except Exception as err:
        logger.exception("Failed to fetch account info for auto-trade check")
        await log_autotrade_decision(pair, best.strategy, "error", str(err), dry_run=settings.dry_run)
        return

    await add_account_snapshot(account.balance, account.equity)
    backtests = scheduler_state.latest_backtests.get(f"{market}:{pair}", {})
    bt_result = backtests.get(best.strategy)

    allowed, reason = can_auto_execute(best, pair, account.balance, scheduler_state.risk_config,
                                        scheduler_state.risk_state, bt_result)

    if not allowed:
        await log_autotrade_decision(pair, best.strategy, "blocked", reason, dry_run=settings.dry_run)
        return

    try:
        spec = await scheduler_state.broker.get_symbol_specification(pair)
        sizing = calculate_position_size(account.balance, scheduler_state.risk_config.risk_per_trade_pct,
                                          best.entry, best.stop, contract_size=spec.get("contractSize", 1))
        if not sizing or not sizing["volume"]:
            await log_autotrade_decision(pair, best.strategy, "error", "Position sizing failed.", dry_run=settings.dry_run)
            return

        result = await scheduler_state.broker.place_market_order(
            symbol=pair, direction=best.direction.value, volume=sizing["volume"],
            stop_loss=best.stop, take_profit=best.tp1,
        )
        action = "executed" if result.success else "error"
        await log_autotrade_decision(pair, best.strategy, action, result.message,
                                      {"direction": best.direction.value, "entry": best.entry, "stop": best.stop},
                                      dry_run=settings.dry_run)
        if result.success:
            await add_journal_entry({
                "id": result.position_id or f"auto-{datetime.now(timezone.utc).timestamp()}",
                "pair": pair, "market": market, "direction": best.direction.value, "strategy": best.strategy,
                "entry": best.entry, "stop": best.stop, "target": best.tp1,
                "notes": f"Auto-executed ({'dry run' if settings.dry_run else 'LIVE'}). {best.reason}",
                "auto_traded": 1, "broker_position_id": result.position_id,
            })
            await notify(format_autotrade_alert(pair, action, result.message, settings.dry_run))
        await notify(format_signal_alert(pair, best))
    except Exception as err:
        logger.exception("Auto-execution failed for %s %s", pair, best.strategy)
        await log_autotrade_decision(pair, best.strategy, "error", str(err), dry_run=settings.dry_run)


async def run_scan_cycle():
    for pair in settings.crypto_pairs:
        try:
            signals = await scan_pair(Market.CRYPTO.value, pair)
            await maybe_auto_execute(Market.CRYPTO.value, pair, signals)
        except Exception:
            logger.exception("Scan failed for crypto:%s", pair)

    try:
        synthetic_pairs = deriv_client.known_symbols or await deriv_client.load_symbol_list()
        for pair in synthetic_pairs[:10]:  # cap to avoid hammering the WS on every cycle
            try:
                signals = await scan_pair(Market.SYNTHETIC.value, pair)
                await maybe_auto_execute(Market.SYNTHETIC.value, pair, signals)
            except Exception:
                logger.exception("Scan failed for synthetic:%s", pair)
    except Exception:
        logger.exception("Failed to load Deriv symbol list")

    scheduler_state.last_scan_at = datetime.now(timezone.utc)


async def scheduler_loop():
    scheduler_state.running = True
    logger.info("Scheduler started -- scanning every %ss", settings.scan_interval_seconds)
    while scheduler_state.running:
        try:
            await run_scan_cycle()
        except Exception:
            logger.exception("Scan cycle failed unexpectedly")
        await asyncio.sleep(settings.scan_interval_seconds)


def stop_scheduler():
    scheduler_state.running = False
