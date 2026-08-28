"""Core data models -- mirror the JS Candle/Signal structures field-for-field."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Market(str, Enum):
    CRYPTO = "crypto"
    SYNTHETIC = "synthetic"


class Timeframe(str, Enum):
    D1 = "D1"; H4 = "H4"; H1 = "H1"; M15 = "M15"; M5 = "M5"


TIMEFRAMES = [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5]


class Direction(str, Enum):
    BUY = "BUY"; SELL = "SELL"; WAIT = "WAIT"


@dataclass
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float

    @property
    def is_bullish(self) -> bool: return self.close >= self.open
    @property
    def is_bearish(self) -> bool: return self.close < self.open
    @property
    def body_high(self) -> float: return max(self.open, self.close)
    @property
    def body_low(self) -> float: return min(self.open, self.close)
    @property
    def body_size(self) -> float: return abs(self.close - self.open)
    @property
    def range_size(self) -> float: return self.high - self.low


CandleSet = dict[Timeframe, list[Candle]]


@dataclass
class Confirmation:
    name: str
    passed: bool


@dataclass
class Signal:
    strategy: str
    source: str
    direction: Direction
    confidence: float = 20
    reason: str = ""
    entry: Optional[float] = None
    stop: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    rr: Optional[float] = None
    confirmations: list[Confirmation] = field(default_factory=list)
    is_pending: bool = False
    pending_direction: Optional[str] = None
    is_error: bool = False
    confluence_score: float = 0
    probability_score: float = 0
    risk_score: float = 0
    grade: str = "B"
    grade_label: str = "B"


def wait_signal(strategy: str, source: str, reason: str, pending: Optional[dict] = None) -> Signal:
    sig = Signal(strategy=strategy, source=source, direction=Direction.WAIT, reason=reason)
    if pending and pending.get("entry") is not None and pending.get("stop") is not None:
        sig.entry = pending.get("entry")
        sig.stop = pending.get("stop")
        sig.tp1 = pending.get("tp1")
        sig.tp2 = pending.get("tp2")
        sig.tp3 = pending.get("tp3")
        sig.rr = pending.get("rr")
        sig.is_pending = True
        sig.pending_direction = pending.get("direction")
    return sig
