"""Strategy registry -- all 10 strategies, run together with per-strategy error isolation."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable, Optional
from app.models import CandleSet, Direction, Signal
from app.strategies import breaker_mitigation, crt_po3, fair_value_gap, liquidity_sweep_mss
from app.strategies import malaysian_snr, order_block, premium_discount_eqhl, supply_demand

logger = logging.getLogger(__name__)


@dataclass
class StrategyEntry:
    name: str
    source: str
    fn: Callable[[CandleSet], Optional[Signal]]
    enabled: bool = True


STRATEGY_REGISTRY: list[StrategyEntry] = [
    StrategyEntry("order_block_rto", order_block.SOURCE, order_block.evaluate),
    StrategyEntry("breaker_block", breaker_mitigation.BREAKER_SOURCE, breaker_mitigation.evaluate_breaker_block),
    StrategyEntry("mitigation_block", breaker_mitigation.MITIGATION_SOURCE, breaker_mitigation.evaluate_mitigation_block),
    StrategyEntry("fair_value_gap", fair_value_gap.SOURCE, fair_value_gap.evaluate),
    StrategyEntry("crt_power_of_3", crt_po3.SOURCE, crt_po3.evaluate),
    StrategyEntry("supply_demand_zone", supply_demand.SOURCE, supply_demand.evaluate),
    StrategyEntry("liquidity_sweep_mss", liquidity_sweep_mss.SOURCE, liquidity_sweep_mss.evaluate),
    StrategyEntry("premium_discount_ote", premium_discount_eqhl.OTE_SOURCE, premium_discount_eqhl.evaluate_premium_discount_ote),
    StrategyEntry("equal_highs_lows", premium_discount_eqhl.EQHL_SOURCE, premium_discount_eqhl.evaluate_equal_highs_lows),
    StrategyEntry("malaysian_snr", malaysian_snr.SOURCE, malaysian_snr.evaluate),
]


def run_engine(candles: CandleSet) -> list[Signal]:
    results: list[Signal] = []
    for entry in STRATEGY_REGISTRY:
        if not entry.enabled:
            continue
        try:
            sig = entry.fn(candles)
            if sig is not None:
                results.append(sig)
        except Exception:
            logger.exception("Strategy %s threw an error", entry.name)
            results.append(Signal(
                strategy=entry.name, source=entry.source, direction=Direction.WAIT, confidence=0,
                reason="This strategy hit an internal error while evaluating and was skipped for this scan.",
                is_error=True,
            ))
    return results
