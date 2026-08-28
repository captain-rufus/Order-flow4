"""Structure primitives shared by every strategy. Port of the JS structure.js."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from app.models import Candle


@dataclass
class SwingPoint:
    index: int
    price: float
    is_high: bool


def find_swing_points(candles: list[Candle], lookback: int = 2) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        window = candles[i - lookback: i + lookback + 1]
        c = candles[i]
        if c.high == max(w.high for w in window):
            swings.append(SwingPoint(i, c.high, True))
        if c.low == min(w.low for w in window):
            swings.append(SwingPoint(i, c.low, False))
    return swings


def read_trend(swings: list[SwingPoint]) -> str:
    highs = [s for s in swings if s.is_high]
    lows = [s for s in swings if not s.is_high]
    if len(highs) < 2 or len(lows) < 2:
        return "ranging"
    higher_highs = highs[-1].price > highs[-2].price
    higher_lows = lows[-1].price > lows[-2].price
    lower_highs = highs[-1].price < highs[-2].price
    lower_lows = lows[-1].price < lows[-2].price
    if higher_highs and higher_lows:
        return "bullish"
    if lower_highs and lower_lows:
        return "bearish"
    return "ranging"


def avg_range(candles: list[Candle], n: int = 20) -> float:
    sl = candles[-n:]
    if not sl:
        return 0.0
    return sum(c.range_size for c in sl) / len(sl)


def has_displacement(candle: Candle, avg_r: float, min_mult: float = 1.3) -> bool:
    return candle.range_size >= avg_r * min_mult


def has_recent_liquidity_sweep(candles: list[Candle], swings: list[SwingPoint], lookback: int = 5) -> bool:
    highs = [s for s in swings if s.is_high]
    lows = [s for s in swings if not s.is_high]
    recent = candles[-lookback:]
    prior_high = highs[-1].price if highs else None
    prior_low = lows[-1].price if lows else None
    swept_high = prior_high is not None and any(c.high > prior_high and c.close < prior_high for c in recent)
    swept_low = prior_low is not None and any(c.low < prior_low and c.close > prior_low for c in recent)
    return swept_high or swept_low


def faster_timeframe_agrees(direction: str, faster_candles: Optional[list[Candle]], lookback: int = 10) -> bool:
    if not faster_candles or len(faster_candles) < lookback:
        return True
    recent = faster_candles[-lookback:]
    net_move = recent[-1].close - recent[0].open
    bullish_count = sum(1 for c in recent if c.is_bullish)
    if direction == "BUY":
        return net_move >= 0 or bullish_count >= (lookback + 1) // 2
    return net_move <= 0 or bullish_count <= lookback // 2
