"""Confluence scoring, A+/A/B grading, and backtest-weighted grade adjustment."""
from __future__ import annotations
from app.models import Direction, Signal

MIN_BACKTEST_SAMPLE = 5
BACKTEST_WINRATE_WARNING_THRESHOLD = 40


def compute_scores(signal: Signal) -> None:
    confs = signal.confirmations
    passed = sum(1 for c in confs if c.passed)
    total = len(confs) or 1
    confluence_score = round((passed / total) * 100)
    rr_num = signal.rr or 0
    probability_score = min(95, round(signal.confidence * 0.7 + confluence_score * 0.3))
    risk_score = max(5, round(100 - min(rr_num, 6) / 6 * 100))

    grade = "B"
    if signal.confidence >= 70 and rr_num >= 3 and confluence_score >= 80:
        grade = "Aplus"
    elif signal.confidence >= 55 and rr_num >= 2 and confluence_score >= 60:
        grade = "A"

    signal.confluence_score = confluence_score
    signal.probability_score = probability_score
    signal.risk_score = risk_score
    signal.grade = grade
    signal.grade_label = "A+" if grade == "Aplus" else grade


def apply_backtest_to_grading(signals: list[Signal], backtest_results: dict) -> None:
    for signal in signals:
        if signal.direction == Direction.WAIT or signal.is_error:
            continue
        bt = backtest_results.get(signal.strategy)
        if not bt or bt.get("total", 0) < MIN_BACKTEST_SAMPLE:
            continue
        win_rate = bt.get("win_rate") or 0

        blended = round(signal.probability_score * 0.55 + win_rate * 0.45)
        grade = signal.grade
        if win_rate < BACKTEST_WINRATE_WARNING_THRESHOLD:
            grade = "B"
        elif win_rate >= 65 and signal.grade == "A":
            grade = "Aplus"
        elif win_rate < 55 and signal.grade == "Aplus":
            grade = "A"

        signal.probability_score = min(95, blended)
        signal.grade = grade
        signal.grade_label = "A+" if grade == "Aplus" else grade
