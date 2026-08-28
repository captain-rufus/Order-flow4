"""Liquidity Sweep + Market Structure Shift. Source: Liquidity Concepts (Forex Trading XL) + Defining Liquidity."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import avg_range, faster_timeframe_agrees, find_swing_points, has_displacement

SOURCE = "Liquidity Concepts (Forex Trading XL) + Defining Liquidity"


def evaluate(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.H4)
    ltf = candles.get(Timeframe.H1)
    if not htf or not ltf or len(htf) < 20:
        return None
    swings = find_swing_points(htf)
    highs = [s for s in swings if s.is_high]
    lows = [s for s in swings if not s.is_high]
    if len(highs) < 2 or len(lows) < 2:
        return None
    last_high, prev_high = highs[-1], highs[-2]
    last_low, prev_low = lows[-1], lows[-2]

    swept_high_no_close = any(c.high > prev_high.price and c.close < prev_high.price for c in htf[last_high.index + 1:])
    swept_low_no_close = any(c.low < prev_low.price and c.close > prev_low.price for c in htf[last_low.index + 1:])
    confirmations = [Confirmation("liquidity_sweep_detected", swept_high_no_close or swept_low_no_close)]
    if not swept_high_no_close and not swept_low_no_close:
        return None

    bearish_mss = swept_high_no_close
    ar = avg_range(htf)
    mss_candle = htf[-1]
    mss_confirmed = mss_candle.close < last_low.price if bearish_mss else mss_candle.close > last_high.price
    displaced = has_displacement(mss_candle, ar)
    confirmations.append(Confirmation("mss_close_beyond_opposite_swing", mss_confirmed))
    confirmations.append(Confirmation("displacement_candle", displaced))

    ls_direction = "SELL" if bearish_mss else "BUY"
    ls_entry = last_low.price if bearish_mss else last_high.price
    ls_stop = last_high.price if bearish_mss else last_low.price
    ls_risk = abs(ls_entry - ls_stop)
    ls_sign = -1 if bearish_mss else 1
    ls_pending = {"direction": ls_direction, "entry": ls_entry, "stop": ls_stop,
                  "tp1": ls_entry + ls_risk * 2 * ls_sign, "tp2": ls_entry + ls_risk * 3.5 * ls_sign,
                  "tp3": ls_entry + ls_risk * 6 * ls_sign, "rr": 2}
    if not (mss_confirmed and displaced):
        return wait_signal("liquidity_sweep_mss", SOURCE,
            "Liquidity swept, waiting for a Market Structure Shift with real displacement before entering.", ls_pending)

    last_price = ltf[-1].close
    direction = "SELL" if bearish_mss else "BUY"
    m15_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.M15))
    confirmations.append(Confirmation("m15_momentum_agrees", m15_agrees))
    if not m15_agrees:
        stop = (last_high.price if swept_high_no_close else mss_candle.high) if bearish_mss else \
               (last_low.price if swept_low_no_close else mss_candle.low)
        risk = abs(last_price - stop)
        return wait_signal("liquidity_sweep_mss", SOURCE,
            "Liquidity swept and MSS confirmed, but M15 momentum currently disagrees — waiting for alignment.",
            {"direction": direction, "entry": last_price, "stop": stop,
             "tp1": last_price + risk * 2 * ls_sign, "tp2": last_price + risk * 3.5 * ls_sign,
             "tp3": last_price + risk * 6 * ls_sign, "rr": 2})

    entry = last_price
    stop = (last_high.price if swept_high_no_close else mss_candle.high) if bearish_mss else \
           (last_low.price if swept_low_no_close else mss_candle.low)
    risk = abs(entry - stop)
    sign = -1 if bearish_mss else 1
    if not risk:
        return None
    return Signal(
        strategy="liquidity_sweep_mss", source=SOURCE,
        direction=Direction.SELL if bearish_mss else Direction.BUY, confidence=70,
        reason=f"{'Buy-side' if bearish_mss else 'Sell-side'} liquidity swept (wick beyond prior swing, no close through) then a displaced Market Structure Shift confirmed the reversal, with M15 momentum agreement.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
