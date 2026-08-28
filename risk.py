"""Risk management for auto-trading: position sizing, daily/weekly loss
circuit breakers, max concurrent trades, cooldown after losses, duplicate
trade prevention. Err on the side of NOT trading on a marginal setup."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 2.0
    max_daily_loss_pct: float = 6.0
    max_weekly_loss_pct: float = 12.0
    max_concurrent_trades: int = 5
    max_spread_pct: float = 0.5
    cooldown_minutes_after_loss: int = 30
    min_grade: str = "Aplus"
    min_backtest_sample: int = 5
    min_backtest_winrate: float = 50.0


def calculate_position_size(balance: float, risk_pct: float, entry: float, stop: float,
                             contract_size: float = 1.0) -> dict | None:
    if entry is None or stop is None or entry == stop:
        return None
    risk_amount = (risk_pct / 100.0) * balance
    price_diff = abs(entry - stop)
    if price_diff <= 0:
        return None
    volume = risk_amount / (price_diff * contract_size) if contract_size else None
    return {"risk_amount": round(risk_amount, 2), "volume": round(volume, 2) if volume else None}


@dataclass
class TradeRecord:
    pair: str
    strategy: str
    opened_at: datetime
    closed_at: datetime | None = None
    outcome: str = "open"
    pnl: float = 0.0


@dataclass
class RiskState:
    starting_balance_today: float = 0.0
    starting_balance_this_week: float = 0.0
    trades: list[TradeRecord] = field(default_factory=list)
    kill_switch: bool = False

    def open_trades(self) -> list[TradeRecord]:
        return [t for t in self.trades if t.outcome == "open"]

    def daily_loss_pct(self, current_balance: float) -> float:
        if self.starting_balance_today <= 0:
            return 0.0
        return max(0.0, (self.starting_balance_today - current_balance) / self.starting_balance_today * 100)

    def weekly_loss_pct(self, current_balance: float) -> float:
        if self.starting_balance_this_week <= 0:
            return 0.0
        return max(0.0, (self.starting_balance_this_week - current_balance) / self.starting_balance_this_week * 100)

    def in_cooldown(self, pair: str, cooldown_minutes: int) -> bool:
        losses = [t for t in self.trades if t.pair == pair and t.outcome == "loss" and t.closed_at]
        if not losses:
            return False
        last_loss = max(losses, key=lambda t: t.closed_at)
        return datetime.now(timezone.utc) - last_loss.closed_at < timedelta(minutes=cooldown_minutes)

    def has_open_trade(self, pair: str, strategy: str) -> bool:
        return any(t.pair == pair and t.strategy == strategy and t.outcome == "open" for t in self.trades)


def can_auto_execute(signal, pair: str, current_balance: float, risk_cfg: RiskConfig,
                      risk_state: RiskState, backtest_result: dict | None,
                      spread_pct: float | None = None) -> tuple[bool, str]:
    if risk_state.kill_switch:
        return False, "Kill switch is engaged."
    if risk_state.daily_loss_pct(current_balance) >= risk_cfg.max_daily_loss_pct:
        return False, f"Daily loss limit reached ({risk_cfg.max_daily_loss_pct}%)."
    if risk_state.weekly_loss_pct(current_balance) >= risk_cfg.max_weekly_loss_pct:
        return False, f"Weekly loss limit reached ({risk_cfg.max_weekly_loss_pct}%)."
    if len(risk_state.open_trades()) >= risk_cfg.max_concurrent_trades:
        return False, f"Max concurrent trades reached ({risk_cfg.max_concurrent_trades})."
    if risk_state.in_cooldown(pair, risk_cfg.cooldown_minutes_after_loss):
        return False, f"{pair} is in a post-loss cooldown ({risk_cfg.cooldown_minutes_after_loss} min)."
    if risk_state.has_open_trade(pair, signal.strategy):
        return False, f"Already have an open {signal.strategy} trade on {pair} — duplicate prevention."

    grade_rank = {"Aplus": 3, "A": 2, "B": 1}
    min_rank = grade_rank.get(risk_cfg.min_grade, 3)
    if grade_rank.get(signal.grade, 0) < min_rank:
        return False, f"Grade {signal.grade_label} is below the auto-trade minimum ({risk_cfg.min_grade})."

    if not backtest_result or backtest_result.get("total", 0) < risk_cfg.min_backtest_sample:
        return False, "Not enough backtested history on this pair for this strategy yet."
    if (backtest_result.get("win_rate") or 0) < risk_cfg.min_backtest_winrate:
        return False, (f"Backtested win rate ({backtest_result.get('win_rate')}%) is below the auto-trade "
                        f"minimum ({risk_cfg.min_backtest_winrate}%).")

    if spread_pct is not None and spread_pct > risk_cfg.max_spread_pct:
        return False, f"Spread ({spread_pct:.2f}%) exceeds the max allowed ({risk_cfg.max_spread_pct}%)."

    return True, "All checks passed."
