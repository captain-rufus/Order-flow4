"""Walk-forward backtest validation -- no lookahead, checks whether each past
signal would have hit its stop or TP1 first using the real candles that followed."""
from __future__ import annotations
from app.grading import MIN_BACKTEST_SAMPLE
from app.models import Candle, CandleSet, Direction, Timeframe
from app.strategies.registry import STRATEGY_REGISTRY


def simulate_trade_forward(entry, stop, tp1, direction: str, future_candles: list[Candle]):
    if entry is None or stop is None or tp1 is None:
        return None
    risk = abs(entry - stop)
    if not risk:
        return None
    is_buy = direction == "BUY"
    for c in future_candles:
        hit_stop = c.low <= stop if is_buy else c.high >= stop
        hit_tp1 = c.high >= tp1 if is_buy else c.low <= tp1
        if hit_stop:
            return {"outcome": "loss", "r": -1.0}
        if hit_tp1:
            return {"outcome": "win", "r": abs(tp1 - entry) / risk}
    return {"outcome": "open", "r": 0.0}


def backtest_strategy_on_pair(strategy_fn, full_candles: CandleSet, warmup: int = 40, max_lookahead: int = 60) -> dict | None:
    entry_candles = full_candles.get(Timeframe.H1)
    if not entry_candles or len(entry_candles) <= warmup:
        return None
    ratios = {tf: len(cs) / len(entry_candles) for tf, cs in full_candles.items()}
    trades = []
    for i in range(warmup, len(entry_candles)):
        known_by_tf: CandleSet = {}
        for tf, cs in full_candles.items():
            known_count = max(1, int((i + 1) * ratios[tf]))
            known_by_tf[tf] = cs[:known_count]
        try:
            signal = strategy_fn(known_by_tf)
        except Exception:
            continue
        if not signal or signal.direction == Direction.WAIT:
            continue
        future = entry_candles[i + 1:i + 1 + max_lookahead]
        result = simulate_trade_forward(signal.entry, signal.stop, signal.tp1, signal.direction.value, future)
        if result and result["outcome"] != "open":
            trades.append(result)

    wins = sum(1 for t in trades if t["outcome"] == "win")
    total = len(trades)
    if not total:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": None, "avg_r": None}
    return {"total": total, "wins": wins, "losses": total - wins,
            "win_rate": round(wins / total * 100), "avg_r": round(sum(t["r"] for t in trades) / total, 2)}


def run_all_backtests(candles: CandleSet) -> dict:
    results = {}
    for entry in STRATEGY_REGISTRY:
        if not entry.enabled:
            continue
        results[entry.name] = backtest_strategy_on_pair(entry.fn, candles)
    return results


def backtest_verdict(result: dict | None) -> dict:
    if not result or result["total"] < MIN_BACKTEST_SAMPLE:
        return {"label": "Not enough history yet", "tone": "wait", "reliable": False}
    if result["win_rate"] < 40:
        return {"label": f"{result['wins']}W-{result['losses']}L ({result['win_rate']}%) — losing track record here", "tone": "sell", "reliable": True}
    return {"label": f"{result['wins']}W-{result['losses']}L ({result['win_rate']}%) on this pair", "tone": "buy", "reliable": True}
