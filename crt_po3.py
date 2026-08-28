"""CRT + Power of 3 + Turtle Soup. Source: CRT METHOD + ict-power-of-3 + mastering-crt-by-maher."""
from __future__ import annotations
from app.models import CandleSet, Confirmation, Direction, Signal, Timeframe, wait_signal
from app.strategies.structure import faster_timeframe_agrees

SOURCE = "CRT METHOD + ict-power-of-3 + mastering-crt-by-maher"


def evaluate(candles: CandleSet) -> Signal | None:
    htf = candles.get(Timeframe.D1)
    if not htf or len(htf) < 5:
        return None
    ref, manip, dist = htf[-3], htf[-2], htf[-1]
    swept_high = manip.high > ref.high
    swept_low = manip.low < ref.low
    confirmations = [Confirmation("crt_range_identified", True)]
    if not swept_high and not swept_low:
        return None
    sweep_above = swept_high
    confirmations.append(Confirmation("manipulation_sweep", True))
    level = ref.high if sweep_above else ref.low
    closed_back = manip.close < level if sweep_above else manip.close > level
    confirmations.append(Confirmation("tbs_body_close_reclaim", closed_back))

    crt_direction = "SELL" if sweep_above else "BUY"
    crt_stop = manip.high if sweep_above else manip.low
    crt_risk = abs(dist.close - crt_stop)
    crt_sign = -1 if sweep_above else 1
    crt_pending = {"direction": crt_direction, "entry": dist.close, "stop": crt_stop,
                   "tp1": dist.close + crt_risk * 2 * crt_sign, "tp2": dist.close + crt_risk * 3.5 * crt_sign,
                   "tp3": dist.close + crt_risk * 6 * crt_sign, "rr": 2}
    if not closed_back:
        return wait_signal("crt_power_of_3", SOURCE,
            "Only a wick-only (TWS) reclaim seen — low probability. Waiting for a body-close (TBS) reclaim.", crt_pending)

    direction = "SELL" if sweep_above else "BUY"
    h4_agrees = faster_timeframe_agrees(direction, candles.get(Timeframe.H4))
    confirmations.append(Confirmation("h4_momentum_agrees", h4_agrees))
    if not h4_agrees:
        return wait_signal("crt_power_of_3", SOURCE,
            "Daily CRT distribution confirmed, but H4 momentum currently disagrees — waiting for alignment.", crt_pending)

    entry = dist.close
    stop = manip.high if sweep_above else manip.low
    risk = abs(entry - stop)
    sign = -1 if sweep_above else 1
    return Signal(
        strategy="crt_power_of_3", source=SOURCE,
        direction=Direction.SELL if sweep_above else Direction.BUY, confidence=72,
        reason=f"Power of 3 distribution phase confirmed: CRT range swept ({'high' if sweep_above else 'low'}) with a TBS (body-close) reclaim, H4 momentum agrees.",
        entry=entry, stop=stop, tp1=entry + risk * 2 * sign, tp2=entry + risk * 3.5 * sign,
        tp3=entry + risk * 6 * sign, rr=2, confirmations=confirmations,
    )
