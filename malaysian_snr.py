"""Malaysian SNR -- line-chart Support & Resistance with fresh/unfresh level tracking."""
from __future__ import annotations
from dataclasses import dataclass
from app.models import Candle, CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import avg_range, faster_timeframe_agrees, find_swing_points, read_trend

SOURCE = "Malaysian SNR (line-chart S&R, fresh/unfresh levels)"


@dataclass
class Pivot:
    index: int
    price: float
    is_peak: bool


def find_close_line_pivots(candles: list[Candle], lookback: int = 3) -> list[Pivot]:
    pivots = []
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback:i + lookback + 1]
        c = candles[i].close
        closes = [w.close for w in window]
        if c == max(closes) and c != min(closes):
            pivots.append(Pivot(i, c, True))
        if c == min(closes) and c != max(closes):
            pivots.append(Pivot(i, c, False))
    return pivots


def is_level_fresh(candles: list[Candle], pivot: Pivot) -> bool:
    after = candles[pivot.index + 1:]
    if pivot.is_peak:
        return not any(c.high >= pivot.price for c in after)
    return not any(c.low <= pivot.price for c in after)


def evaluate(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.D1)
    ltf = candles.get(Timeframe.H1)
    if not htf or not ltf or len(htf) < 20:
        return None
    wick_swings = find_swing_points(htf)
    trend = read_trend(wick_swings)
    confirmations = [Confirmation("storyline_trend_read", trend != "ranging")]
    if trend == "ranging":
        return None

    want_support = trend == "bullish"
    pivots = [p for p in find_close_line_pivots(htf) if p.is_peak != want_support]
    confirmations.append(Confirmation("snr_level_found_matching_storyline", len(pivots) > 0))
    if not pivots:
        return None

    fresh_levels = [p for p in pivots if is_level_fresh(htf, p)]
    confirmations.append(Confirmation("level_is_fresh", len(fresh_levels) > 0))
    if not fresh_levels:
        return wait_signal("malaysian_snr", SOURCE,
            f"{'Support' if want_support else 'Resistance'} levels found on the Daily close-line, but none are still fresh (untested by a wick).")

    level = fresh_levels[-1]
    last_price = ltf[-1].close
    ar = avg_range(htf)
    near_level = abs(last_price - level.price) <= ar * 0.6
    confirmations.append(Confirmation("price_at_fresh_level", near_level))

    snr_direction = "BUY" if want_support else "SELL"
    snr_stop = level.price - ar * 0.3 if want_support else level.price + ar * 0.3
    snr_risk = abs(level.price - snr_stop)
    snr_sign = 1 if want_support else -1
    snr_pending = {"direction": snr_direction, "entry": level.price, "stop": snr_stop,
                   "tp1": level.price + snr_risk * 2 * snr_sign, "tp2": level.price + snr_risk * 3.5 * snr_sign,
                   "tp3": level.price + snr_risk * 6 * snr_sign, "rr": 2}
    if not near_level:
        return wait_signal("malaysian_snr", SOURCE,
            f"Fresh {'V-level (support)' if want_support else 'A-level (resistance)'} identified on the Daily storyline, waiting for price to reach it.", snr_pending)

    direction = "BUY" if want_support else "SELL"
    ltf_confirms = faster_timeframe_agrees(direction, ltf[-6:])
    confirmations.append(Confirmation("ltf_rejection_confirmation", ltf_confirms))
    if not ltf_confirms:
        risk = abs(last_price - snr_stop)
        return wait_signal("malaysian_snr", SOURCE,
            f"Price is at a fresh {'support' if want_support else 'resistance'} level, waiting for H1 to actually confirm the rejection before entering.",
            {"direction": direction, "entry": last_price, "stop": snr_stop,
             "tp1": last_price + risk * 2 * snr_sign, "tp2": last_price + risk * 3.5 * snr_sign,
             "tp3": last_price + risk * 6 * snr_sign, "rr": 2})

    entry = last_price
    stop = snr_stop
    risk = abs(entry - stop)
    sign = 1 if want_support else -1
    if not risk:
        return None
    return Signal(
        strategy="malaysian_snr", source=SOURCE,
        direction=Direction.BUY if want_support else Direction.SELL, confidence=63,
        reason=f"Daily storyline is {trend} — only trading with-trend pullbacks per Malaysian SNR. Price reacted at a fresh {'V-level (support)' if want_support else 'A-level (resistance)'} on the close-price line chart, confirmed by H1 rejection.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
