"""Fair Value Gap (BISI/SIBI + CE). Source: Fair Value Gaps by Alberuni Trader."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import avg_range, faster_timeframe_agrees, find_swing_points, has_displacement, has_recent_liquidity_sweep

SOURCE = "Fair Value Gaps by Alberuni Trader"


def evaluate(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.H4)
    ltf = candles.get(Timeframe.H1)
    if not htf or not ltf or len(htf) < 10:
        return None
    swings = find_swing_points(htf)
    fvgs = []
    for i in range(2, len(htf)):
        c1, c3 = htf[i - 2], htf[i]
        if c1.high < c3.low:
            fvgs.append({"high": c3.low, "low": c1.high, "bullish": True})
        elif c1.low > c3.high:
            fvgs.append({"high": c1.low, "low": c3.high, "bullish": False})
    confirmations = [Confirmation("fvg_present", len(fvgs) > 0)]
    if not fvgs:
        return None
    zone = fvgs[-1]

    ar = avg_range(htf)
    displaced = has_displacement(htf[-1], ar)
    stop_hunt = has_recent_liquidity_sweep(htf, swings)
    confirmations.append(Confirmation("stop_hunt_or_poi", stop_hunt))
    confirmations.append(Confirmation("mss_with_displacement", displaced))

    ce = (zone["high"] + zone["low"]) / 2
    fvg_direction = "BUY" if zone["bullish"] else "SELL"
    fvg_stop = zone["low"] if zone["bullish"] else zone["high"]
    fvg_risk = abs(ce - fvg_stop)
    fvg_sign = 1 if zone["bullish"] else -1
    fvg_pending = {"direction": fvg_direction, "entry": ce, "stop": fvg_stop,
                   "tp1": ce + fvg_risk * 2 * fvg_sign, "tp2": ce + fvg_risk * 3.5 * fvg_sign,
                   "tp3": ce + fvg_risk * 6 * fvg_sign, "rr": 2}
    if not (stop_hunt and displaced):
        return wait_signal("fair_value_gap", SOURCE,
            "Needs BOTH a stop hunt/POI AND an MSS with displacement (Alberuni Trader rule) — not yet confirmed.", fvg_pending)

    last_price = ltf[-1].close
    tolerance = (zone["high"] - zone["low"]) * 0.2
    in_zone = abs(last_price - ce) <= tolerance
    confirmations.append(Confirmation("price_at_ce", in_zone))
    if not in_zone:
        return wait_signal("fair_value_gap", SOURCE,
            "HTF FVG confirmed, waiting for price to reach the Consequent Encroachment (50%).", fvg_pending)

    direction = "BUY" if zone["bullish"] else "SELL"
    m15_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.M15))
    confirmations.append(Confirmation("m15_momentum_agrees", m15_agrees))
    if not m15_agrees:
        return wait_signal("fair_value_gap", SOURCE,
            "HTF FVG confirmed at CE, but M15 momentum currently disagrees — waiting for alignment.", fvg_pending)

    entry = last_price
    stop = zone["low"] if zone["bullish"] else zone["high"]
    risk = abs(entry - stop)
    sign = 1 if zone["bullish"] else -1
    return Signal(
        strategy="fair_value_gap", source=SOURCE,
        direction=Direction.BUY if zone["bullish"] else Direction.SELL, confidence=70,
        reason="HTF FVG (BISI/SIBI) with displacement confirmed, price at Consequent Encroachment, M15 momentum agrees (Alberuni Trader FVG checklist plus an extra timeframe cross-check).",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
