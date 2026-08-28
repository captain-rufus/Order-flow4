"""Breaker Block (Alberuni Trader) and Mitigation Block (Ali Khan's ICT Bible)."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import avg_range, faster_timeframe_agrees, find_swing_points, has_displacement, has_recent_liquidity_sweep

BREAKER_SOURCE = "Breaker Blocks By Alberuni Trader"
MITIGATION_SOURCE = "The ICT Bible V1 (Ali Khan)"


def evaluate_breaker_block(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.H4)
    ltf = candles.get(Timeframe.H1)
    if not htf or not ltf or len(htf) < 15:
        return None
    swings = find_swing_points(htf)
    lows = [s for s in swings if not s.is_high]
    highs = [s for s in swings if s.is_high]
    zones = []
    for low in lows:
        if not any(c.low < low.price for c in htf[low.index + 1:]):
            continue
        up_candles = [c for c in htf[max(0, low.index - 5):low.index] if c.is_bullish]
        if not up_candles:
            continue
        zones.append({"high": max(c.body_high for c in up_candles), "low": min(c.body_low for c in up_candles), "bullish": True})
    for high in highs:
        if not any(c.high > high.price for c in htf[high.index + 1:]):
            continue
        down_candles = [c for c in htf[max(0, high.index - 5):high.index] if c.is_bearish]
        if not down_candles:
            continue
        zones.append({"high": max(c.body_high for c in down_candles), "low": min(c.body_low for c in down_candles), "bullish": False})
    if not zones:
        return None
    zone = zones[-1]

    ar = avg_range(htf)
    displaced = has_displacement(htf[-1], ar)
    stop_hunt = has_recent_liquidity_sweep(htf, swings)
    confirmations = [Confirmation("stop_hunt_liquidity_sweep", stop_hunt), Confirmation("mss_with_displacement", displaced)]
    zone_direction = "BUY" if zone["bullish"] else "SELL"
    zone_entry = zone["high"] if zone["bullish"] else zone["low"]
    zone_stop = zone["low"] if zone["bullish"] else zone["high"]
    zone_risk = abs(zone_entry - zone_stop)
    zone_sign = 1 if zone["bullish"] else -1
    zone_pending = {"direction": zone_direction, "entry": zone_entry, "stop": zone_stop,
                     "tp1": zone_entry + zone_risk * 2 * zone_sign, "tp2": zone_entry + zone_risk * 3.5 * zone_sign,
                     "tp3": zone_entry + zone_risk * 6 * zone_sign, "rr": 2}
    if not (displaced and stop_hunt):
        return wait_signal("breaker_block", BREAKER_SOURCE,
            "Needs BOTH a stop hunt AND an MSS with displacement (Alberuni Trader rule) — not yet confirmed.", zone_pending)

    last_price = ltf[-1].close
    retested = zone["low"] <= last_price <= zone["high"]
    confirmations.append(Confirmation("retest_of_breaker_body", retested))
    if not retested:
        return wait_signal("breaker_block", BREAKER_SOURCE,
            "Stop hunt + MSS confirmed, waiting for retest of the breaker candle bodies.", zone_pending)

    direction = "BUY" if zone["bullish"] else "SELL"
    m15_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.M15))
    confirmations.append(Confirmation("m15_momentum_agrees", m15_agrees))
    if not m15_agrees:
        return wait_signal("breaker_block", BREAKER_SOURCE,
            "H4/H1 Breaker Block confirmed, but M15 momentum currently disagrees — waiting for alignment.", zone_pending)

    entry = last_price
    stop = zone["low"] if zone["bullish"] else zone["high"]
    risk = abs(entry - stop)
    sign = 1 if zone["bullish"] else -1
    return Signal(
        strategy="breaker_block", source=BREAKER_SOURCE,
        direction=Direction.BUY if zone["bullish"] else Direction.SELL, confidence=75,
        reason="High-probability Breaker Block: HTF liquidity raid + MSS with displacement + retest of breaker candle bodies + M15 momentum agreement (Alberuni Trader checklist plus an extra timeframe cross-check).",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )


def evaluate_mitigation_block(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.H4)
    ltf = candles.get(Timeframe.H1)
    if not htf or not ltf or len(htf) < 15:
        return None
    swings = find_swing_points(htf)
    highs = [s for s in swings if s.is_high]
    lows = [s for s in swings if not s.is_high]
    zone = None
    for i in range(len(highs) - 1):
        h1 = highs[i]
        sub_lows = [l for l in lows if l.index > h1.index]
        if not sub_lows:
            continue
        l1 = sub_lows[0]
        sub_highs = [h for h in highs if h.index > l1.index]
        if not sub_highs:
            continue
        h2 = sub_highs[0]
        if h2.price >= h1.price:
            continue
        if not any(c.low < l1.price for c in htf[h2.index + 1:]):
            continue
        up_candles = [c for c in htf[max(0, l1.index - 5):l1.index] if c.is_bullish]
        if not up_candles:
            continue
        zone = {"high": max(c.body_high for c in up_candles), "low": min(c.body_low for c in up_candles), "bullish": False}

    confirmations = [Confirmation("lower_high_then_reversal", zone is not None)]
    if not zone:
        return None
    last_price = ltf[-1].close
    retested = zone["low"] <= last_price <= zone["high"]
    confirmations.append(Confirmation("retest_of_mitigation_zone", retested))
    m_direction = "BUY" if zone["bullish"] else "SELL"
    m_entry = zone["high"] if zone["bullish"] else zone["low"]
    m_stop = zone["low"] if zone["bullish"] else zone["high"]
    m_risk = abs(m_entry - m_stop)
    m_sign = 1 if zone["bullish"] else -1
    m_pending = {"direction": m_direction, "entry": m_entry, "stop": m_stop,
                 "tp1": m_entry + m_risk * 2 * m_sign, "tp2": m_entry + m_risk * 3.5 * m_sign,
                 "tp3": m_entry + m_risk * 6 * m_sign, "rr": 2}
    if not retested:
        return wait_signal("mitigation_block", MITIGATION_SOURCE,
            "Mitigation Block identified (Lower-High variant), waiting for retest.", m_pending)

    direction = "BUY" if zone["bullish"] else "SELL"
    m15_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.M15))
    confirmations.append(Confirmation("m15_momentum_agrees", m15_agrees))
    if not m15_agrees:
        return wait_signal("mitigation_block", MITIGATION_SOURCE,
            "Mitigation Block confirmed, but M15 momentum currently disagrees — waiting for alignment.", m_pending)

    entry = last_price
    stop = zone["low"] if zone["bullish"] else zone["high"]
    risk = abs(entry - stop)
    sign = 1 if zone["bullish"] else -1
    return Signal(
        strategy="mitigation_block", source=MITIGATION_SOURCE,
        direction=Direction.BUY if zone["bullish"] else Direction.SELL, confidence=55,
        reason="Mitigation Block (Lower-High variant, weaker than a full Breaker) retested, M15 momentum agrees, per Ali Khan's ICT Bible distinction.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
