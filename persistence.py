"""SQLite persistence -- journal, signal history, and auto-trade audit log.
Uses stdlib sqlite3 in a thread pool via asyncio.to_thread, no extra
dependency needed."""
from __future__ import annotations
import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal (
    id TEXT PRIMARY KEY,
    pair TEXT NOT NULL,
    market TEXT NOT NULL,
    direction TEXT NOT NULL,
    strategy TEXT NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    outcome TEXT NOT NULL DEFAULT 'open',
    r_multiple REAL,
    notes TEXT,
    auto_traded INTEGER NOT NULL DEFAULT 0,
    broker_position_id TEXT
);

CREATE TABLE IF NOT EXISTS autotrade_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    pair TEXT NOT NULL,
    strategy TEXT,
    action TEXT NOT NULL,       -- "would_execute" | "executed" | "blocked" | "error"
    reason TEXT,
    signal_json TEXT,
    dry_run INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    balance REAL NOT NULL,
    equity REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_sync():
    with _connect() as conn:
        conn.executescript(SCHEMA)


async def init_db():
    await asyncio.to_thread(init_db_sync)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Journal ----

def add_journal_entry_sync(entry: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO journal (id, pair, market, direction, strategy, entry, stop, target, "
            "opened_at, outcome, notes, auto_traded, broker_position_id) "
            "VALUES (:id, :pair, :market, :direction, :strategy, :entry, :stop, :target, "
            ":opened_at, 'open', :notes, :auto_traded, :broker_position_id)",
            {**entry, "opened_at": entry.get("opened_at", _now())},
        )


async def add_journal_entry(entry: dict) -> None:
    await asyncio.to_thread(add_journal_entry_sync, entry)


def close_journal_entry_sync(entry_id: str, outcome: str, r_multiple: Optional[float]) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE journal SET outcome=?, r_multiple=?, closed_at=? WHERE id=?",
            (outcome, r_multiple, _now(), entry_id),
        )


async def close_journal_entry(entry_id: str, outcome: str, r_multiple: Optional[float]) -> None:
    await asyncio.to_thread(close_journal_entry_sync, entry_id, outcome, r_multiple)


def get_open_trades_sync() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM journal WHERE outcome='open'").fetchall()
        return [dict(r) for r in rows]


async def get_open_trades() -> list[dict]:
    return await asyncio.to_thread(get_open_trades_sync)


def get_journal_sync(limit: int = 200) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM journal ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


async def get_journal(limit: int = 200) -> list[dict]:
    return await asyncio.to_thread(get_journal_sync, limit)


# ---- Auto-trade audit log (every decision, not just executions) ----

def log_autotrade_decision_sync(pair: str, strategy: str, action: str, reason: str,
                                  signal_dict: Optional[dict], dry_run: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO autotrade_audit (timestamp, pair, strategy, action, reason, signal_json, dry_run) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), pair, strategy, action, reason, json.dumps(signal_dict) if signal_dict else None, int(dry_run)),
        )


async def log_autotrade_decision(pair: str, strategy: str, action: str, reason: str,
                                   signal_dict: Optional[dict] = None, dry_run: bool = True) -> None:
    await asyncio.to_thread(log_autotrade_decision_sync, pair, strategy, action, reason, signal_dict, dry_run)


def get_autotrade_audit_sync(limit: int = 200) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM autotrade_audit ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


async def get_autotrade_audit(limit: int = 200) -> list[dict]:
    return await asyncio.to_thread(get_autotrade_audit_sync, limit)


# ---- Account snapshots (for daily/weekly loss tracking) ----

def add_account_snapshot_sync(balance: float, equity: float) -> None:
    with _connect() as conn:
        conn.execute("INSERT INTO account_snapshots (timestamp, balance, equity) VALUES (?, ?, ?)",
                     (_now(), balance, equity))


async def add_account_snapshot(balance: float, equity: float) -> None:
    await asyncio.to_thread(add_account_snapshot_sync, balance, equity)
