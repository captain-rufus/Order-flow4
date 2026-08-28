"""Supply & Demand zones (Frank Miller) -- ERC-validated, independent lineage."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import faster_timeframe_agrees

SOURCE = "Supply and Demand Trading (Frank Miller)"


def _is_erc(c) -> bool:
    return c.range_size > 0 and c.body_size / c.range_size > 0.5


def evaluate(candles: CandleSet) -> Signal | None:
    base = candles.get(Timeframe.D1)
    entry_tf = candles.get(Timeframe.H4)
    if not base or not entry_tf or len(base) < 15:
        return None
    window = base[-15:]
    bullish_run = [c for c in window if c.is_bullish]
    bearish_run = [c for c in window if c.is_bearish]
    bull_ercs = sum(1 for c in bullish_run if _is_erc(c))
    bear_ercs = sum(1 for c in bearish_run if _is_erc(c))
    bias = None
    if bull_ercs >= 2 and bull_ercs >= bear_ercs:
        bias = "bullish"
    elif bear_ercs >= 2:
        bias = "bearish"
    confirmations = [Confirmation("impulse_leg_min_2_ercs", bias is not None)]
    if not bias:
        return None
    is_demand = bias == "bullish"

    impulse_candles = bullish_run if is_demand else bearish_run
    if not impulse_candles:
        return None
    first_impulse_idx = base.index(impulse_candles[0])
    base_window = base[max(0, first_impulse_idx - 4):first_impulse_idx]
    if not base_window:
        return None

    long_tailed = sum(1 for c in base_window if c.range_size > 0 and c.body_size / c.range_size < 0.25)
    confirmations.append(Confirmation("base_not_disqualified", long_tailed < 2))
    if long_tailed >= 2:
        return wait_signal("supply_demand_zone", SOURCE,
            "Candidate zone disqualified: several long-tailed candles (Frank Miller invalid-zone filter).")

    distal = min(c.low for c in base_window) if is_demand else max(c.high for c in base_window)
    proximal = min(c.body_low for c in base_window) if is_demand else max(c.body_high for c in base_window)
    lo, hi = sorted([distal, proximal])
    last_price = entry_tf[-1].close
    at_zone = lo <= last_price <= hi
    confirmations.append(Confirmation("price_at_proximal_line", at_zone))

    sd_direction = "BUY" if is_demand else "SELL"
    sd_risk = abs(proximal - distal)
    sd_sign = 1 if is_demand else -1
    sd_pending = {"direction": sd_direction, "entry": proximal, "stop": distal,
                  "tp1": proximal + sd_risk * 2 * sd_sign, "tp2": proximal + sd_risk * 3.5 * sd_sign,
                  "tp3": proximal + sd_risk * 6 * sd_sign, "rr": 2}
    if not at_zone:
        return wait_signal("supply_demand_zone", SOURCE,
            "Valid zone identified, waiting for price to return to the proximal line.", sd_pending)

    direction = "BUY" if is_demand else "SELL"
    h1_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.H1))
    confirmations.append(Confirmation("h1_momentum_agrees", h1_agrees))
    if not h1_agrees:
        return wait_signal("supply_demand_zone", SOURCE,
            "Zone reached, but H1 momentum currently disagrees — waiting for alignment.", sd_pending)

    entry = proximal
    stop = distal
    risk = abs(entry - stop)
    sign = 1 if is_demand else -1
    return Signal(
        strategy="supply_demand_zone", source=SOURCE,
        direction=Direction.BUY if is_demand else Direction.SELL, confidence=65,
        reason=f"{'Demand' if is_demand else 'Supply'} zone at proximal line, base impulse had ≥2 ERCs, H1 momentum agrees (Frank Miller 3-step identification plus an extra timeframe cross-check).",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
