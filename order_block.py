"""Order Block Return-To-Origin. Source: OB Theory (Lutandula) + RULE BASED TRADING."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import faster_timeframe_agrees, find_swing_points, read_trend

SOURCE = "OB Theory (Lutandula) + RULE BASED TRADING"


def evaluate(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.D1)
    ltf = candles.get(Timeframe.H4)
    if not htf or not ltf or len(htf) < 10:
        return None
    swings = find_swing_points(htf)
    trend = read_trend(swings)
    confirmations = [Confirmation("htf_structure_read", trend != "ranging")]
    if trend == "ranging":
        return wait_signal("order_block_rto", SOURCE, "HTF structure is ranging — no valid bias (RULE BASED TRADING step 1).")

    want_bullish = trend == "bullish"
    lows = [s for s in swings if not s.is_high]
    highs = [s for s in swings if s.is_high]
    zone = None
    if want_bullish:
        for low in lows:
            c = htf[low.index]
            if not c.is_bearish:
                continue
            if any(later.high > c.body_high for later in htf[low.index + 1:]):
                zone = {"high": c.body_high, "low": c.low}
    else:
        for high in highs:
            c = htf[high.index]
            if not c.is_bullish:
                continue
            if any(later.low < c.body_low for later in htf[high.index + 1:]):
                zone = {"high": c.high, "low": c.body_low}

    confirmations.append(Confirmation("validated_source_ob_found", zone is not None))
    if not zone:
        return None

    last_price = ltf[-1].close
    in_poi = zone["low"] <= last_price <= zone["high"]
    confirmations.append(Confirmation("price_returned_to_poi", in_poi))
    if not in_poi:
        pending_entry = zone["high"] if want_bullish else zone["low"]
        pending_stop = zone["low"] if want_bullish else zone["high"]
        risk = abs(pending_entry - pending_stop)
        sign = 1 if want_bullish else -1
        return wait_signal("order_block_rto", SOURCE,
            f"HTF {trend} bias set, waiting for price to return to the Order Block POI.",
            {"direction": "BUY" if want_bullish else "SELL", "entry": pending_entry, "stop": pending_stop,
             "tp1": pending_entry + risk * 2 * sign, "tp2": pending_entry + risk * 3.5 * sign,
             "tp3": pending_entry + risk * 6 * sign, "rr": 2})

    h1_agrees = faster_timeframe_agrees("BUY" if want_bullish else "SELL", candles.get(Timeframe.H1))
    confirmations.append(Confirmation("h1_momentum_agrees", h1_agrees))
    if not h1_agrees:
        pending_stop = zone["low"] if want_bullish else zone["high"]
        risk = abs(last_price - pending_stop)
        sign = 1 if want_bullish else -1
        return wait_signal("order_block_rto", SOURCE,
            "Daily/H4 setup is valid, but H1 momentum is currently pointing the other way — waiting for it to align before entering.",
            {"direction": "BUY" if want_bullish else "SELL", "entry": last_price, "stop": pending_stop,
             "tp1": last_price + risk * 2 * sign, "tp2": last_price + risk * 3.5 * sign,
             "tp3": last_price + risk * 6 * sign, "rr": 2})

    entry = last_price
    stop = zone["low"] if want_bullish else zone["high"]
    risk = abs(entry - stop)
    sign = 1 if want_bullish else -1
    return Signal(
        strategy="order_block_rto", source=SOURCE,
        direction=Direction.BUY if want_bullish else Direction.SELL, confidence=65,
        reason=f"HTF (Daily) {trend} Source Order Block validated, price returned to POI, H1 momentum agrees — 3-step RULE BASED TRADING checklist satisfied plus an extra timeframe cross-check.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
