"""Premium/Discount + OTE, and Equal Highs/Equal Lows."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import avg_range, faster_timeframe_agrees, find_swing_points, read_trend

OTE_SOURCE = "S2TA FOREX G&B SWING + ICT Trading Strategy (OTE)"
EQHL_SOURCE = "Liquidity Concepts (Forex Trading XL) — Equal Highs/Lows"


def evaluate_premium_discount_ote(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.D1)
    ltf = candles.get(Timeframe.H4)
    if not htf or not ltf or len(htf) < 15:
        return None
    swings = find_swing_points(htf)
    trend = read_trend(swings)
    confirmations = [Confirmation("htf_trend_read", trend != "ranging")]
    if trend == "ranging":
        return None

    recent_highs = [s for s in swings if s.is_high][-3:]
    recent_lows = [s for s in swings if not s.is_high][-3:]
    if not recent_highs or not recent_lows:
        return None
    range_high = max(s.price for s in recent_highs)
    range_low = min(s.price for s in recent_lows)
    span = range_high - range_low
    if not span:
        return None

    last_price = ltf[-1].close
    pos_in_range = (last_price - range_low) / span
    want_bullish = trend == "bullish"
    in_discount = pos_in_range <= 0.382
    in_premium = pos_in_range >= 0.618
    ote_aligned = in_discount if want_bullish else in_premium
    confirmations.append(Confirmation("price_in_ote_discount_or_premium_zone", ote_aligned))

    ote_entry_target = range_low + span * (0.382 if want_bullish else 0.618)
    ote_stop = range_low - span * 0.05 if want_bullish else range_high + span * 0.05
    ote_risk = abs(ote_entry_target - ote_stop)
    ote_sign = 1 if want_bullish else -1
    ote_pending = {"direction": "BUY" if want_bullish else "SELL", "entry": ote_entry_target, "stop": ote_stop,
                   "tp1": ote_entry_target + ote_risk * 2 * ote_sign, "tp2": ote_entry_target + ote_risk * 3.5 * ote_sign,
                   "tp3": ote_entry_target + ote_risk * 6 * ote_sign, "rr": 2}
    if not ote_aligned:
        return wait_signal("premium_discount_ote", OTE_SOURCE,
            f"HTF {trend}, but price is at {pos_in_range*100:.0f}% of the range — not yet in the OTE zone (need {'discount (<38%)' if want_bullish else 'premium (>62%)'}).", ote_pending)

    direction = "BUY" if want_bullish else "SELL"
    h1_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.H1))
    confirmations.append(Confirmation("h1_momentum_agrees", h1_agrees))
    if not h1_agrees:
        risk = abs(last_price - ote_stop)
        return wait_signal("premium_discount_ote", OTE_SOURCE,
            "Price is in the OTE zone, but H1 momentum currently disagrees — waiting for alignment.",
            {"direction": direction, "entry": last_price, "stop": ote_stop,
             "tp1": last_price + risk * 2 * ote_sign, "tp2": last_price + risk * 3.5 * ote_sign,
             "tp3": last_price + risk * 6 * ote_sign, "rr": 2})

    entry = last_price
    stop = ote_stop
    risk = abs(entry - stop)
    sign = 1 if want_bullish else -1
    return Signal(
        strategy="premium_discount_ote", source=OTE_SOURCE,
        direction=Direction.BUY if want_bullish else Direction.SELL, confidence=62,
        reason=f"HTF {trend} trend with price at {pos_in_range*100:.0f}% of the dealing range — inside the Optimal Trade Entry zone, H1 momentum agrees.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )


def evaluate_equal_highs_lows(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.H4)
    ltf = candles.get(Timeframe.H1)
    if not htf or not ltf or len(htf) < 20:
        return None
    swings = find_swing_points(htf)
    highs = [s for s in swings if s.is_high]
    lows = [s for s in swings if not s.is_high]
    tolerance = avg_range(htf) * 0.15

    def find_equal_pair(points):
        for i in range(len(points) - 1, 0, -1):
            for j in range(i - 1, -1, -1):
                if abs(points[i].price - points[j].price) <= tolerance:
                    return points[j], points[i]
        return None

    eq_highs = find_equal_pair(highs[-6:])
    eq_lows = find_equal_pair(lows[-6:])
    confirmations = [Confirmation("equal_highs_or_lows_found", bool(eq_highs or eq_lows))]
    if not eq_highs and not eq_lows:
        return None

    last_price = ltf[-1].close
    direction = None
    level = None
    target_set = None
    if eq_highs and last_price < eq_highs[0].price:
        direction, level, target_set = "SELL", eq_highs[1].price, "equal highs (buy-side liquidity)"
    elif eq_lows and last_price > eq_lows[0].price:
        direction, level, target_set = "BUY", eq_lows[1].price, "equal lows (sell-side liquidity)"
    if not direction:
        return None

    near_level = abs(last_price - level) <= tolerance * 2.5
    confirmations.append(Confirmation("price_approaching_equal_liquidity", near_level))
    eq_stop = level * 1.002 if direction == "SELL" else level * 0.998
    eq_risk = abs(level - eq_stop)
    eq_sign = 1 if direction == "BUY" else -1
    eq_pending = {"direction": direction, "entry": level, "stop": eq_stop,
                  "tp1": level + eq_risk * 2 * eq_sign, "tp2": level + eq_risk * 3.5 * eq_sign,
                  "tp3": level + eq_risk * 6 * eq_sign, "rr": 2}
    if not near_level:
        return wait_signal("equal_highs_lows", EQHL_SOURCE,
            f"{target_set} identified as a draw on liquidity, but price hasn't approached it yet.", eq_pending)

    m15 = candles.get(Timeframe.M15)
    already_swept = m15 and any((c.close > level if direction == "SELL" else c.close < level) for c in m15[-5:])
    confirmations.append(Confirmation("m15_liquidity_not_already_taken", not already_swept))
    if already_swept:
        return wait_signal("equal_highs_lows", EQHL_SOURCE, f"{target_set} looks like it was already swept on M15 — this setup is stale.")

    entry = last_price
    stop = level * 1.002 if direction == "SELL" else level * 0.998
    risk = abs(entry - stop)
    sign = 1 if direction == "BUY" else -1
    if not risk:
        return None
    return Signal(
        strategy="equal_highs_lows", source=EQHL_SOURCE,
        direction=Direction.BUY if direction == "BUY" else Direction.SELL, confidence=58,
        reason=f"Price approaching {target_set} — a resting-liquidity magnet, not yet swept on M15. Expect a sweep and reaction on arrival.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
