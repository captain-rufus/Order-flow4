# ORDERFLOW Backend

The real, always-on version of the browser-based signal engine. This runs as
a server process, so it keeps scanning and (optionally) trading whether or
not anyone has a browser tab open — the one thing the client-side version
could never do.

## What's actually the same as the browser tool

All 10 strategies, confluence scoring, A+/A/B grading, and the walk-forward
backtest validation are ported line-for-line from `orderflow.html`. A signal
computed here means exactly the same thing as one computed there. Real data
sources are the same too: Binance's public API for Crypto, Deriv's public
WebSocket for Synthetic Indices, both key-less.

## What's new here

- **Runs continuously** via a background scan loop (`app/scheduler.py`),
  independent of any browser.
- **Real auto-trading**, via MetaApi.cloud's official SDK — token-based
  (not password-based), matching the pattern already described in the
  browser tool's Auto-Trading panel.
- **Risk gates** (`app/risk.py`): daily/weekly loss circuit breakers, max
  concurrent trades, post-loss cooldown, duplicate-trade prevention, and a
  minimum backtested win rate before anything is allowed to auto-execute.
- **A full audit log** of every auto-trade decision — executed, blocked, or
  errored — not just the trades that went through.
- **An emergency kill switch and close-all-positions endpoint**, independent
  of the auto-trade master switch.

## Before you touch DRY_RUN

Read this whole section before changing anything in `.env`.

**`DRY_RUN=true` is the default and it stays that way until you decide
otherwise.** In dry-run mode, every broker action is logged in full detail —
symbol, direction, volume, stop-loss, take-profit — and then **nothing is
sent to any broker**. You can watch the entire decision pipeline (signal →
grading → backtest check → risk gate → position sizing → "order") end to
end without any real-money risk.

**The MetaApi integration in `app/broker/metaapi_adapter.py` has never run
against a live or demo trading account.** I built it against MetaApi's
documented SDK patterns and verified the API shapes before writing it, but
I have no MetaApi account to test against from this environment. "Written
correctly against the docs" and "confirmed working" are different claims —
this is only the first one.

**The recommended path before any real money is at risk:**

1. Create a MetaApi.cloud account and connect a **demo** MT4/MT5 account —
   not a live one — through their dashboard. Get your account token and
   account ID from there.
2. Set `METAAPI_TOKEN` and `METAAPI_ACCOUNT_ID` in `.env`, but leave
   `DRY_RUN=true`. Run the backend and confirm it can fetch real account
   balance/equity via `GET /autotrade/status` and that scans are producing
   sensible signals via `GET /signals/{market}/{pair}`.
3. Set `DRY_RUN=false` **against the demo account only**. Let it run for at
   least a few weeks across different market conditions. Check the audit
   log (`GET /autotrade/audit-log`) after every trade and confirm the
   position sizing, stop-loss, and take-profit it computed match what
   you'd expect by hand.
4. Only after that, consider a live account — and start with the smallest
   `risk_per_trade_pct` you're willing to be wrong about, not the default.

There is no step where this becomes "probably fine, just turn it on." Real
money execution deserves the slow path.

## Setup

```bash
cp .env.example .env
# edit .env

pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or with Docker:

```bash
docker compose up --build
```

## API overview

- `GET /health` — liveness + current dry-run/auto-trade state
- `GET /signals/{market}/{pair}` — run the full engine on one pair right now
  (`market` is `crypto` or `synthetic`)
- `GET /signals/synthetic/symbols` — the live Deriv symbol list
- `GET /autotrade/status` — auto-trade state, risk config, open trade count
- `POST /autotrade/enable` / `POST /autotrade/disable` — master switch
- `POST /autotrade/kill-switch` / `POST /autotrade/kill-switch/release` —
  emergency stop, independent of the master switch
- `POST /autotrade/close-all` — close every open position immediately
- `PUT /autotrade/risk-config` — adjust risk limits without restarting
- `GET /autotrade/audit-log` — every auto-trade decision ever made
- `GET /journal`, `POST /journal`, `POST /journal/{id}/close` — manual and
  auto-logged trade journal

## What hasn't been tested here, and why

This sandbox has no network access, so nothing that requires a live network
call — Binance, Deriv, MetaApi, Telegram, Discord — could be executed
end-to-end from here. What **was** tested with real execution (not just
written and assumed correct):

- All 10 strategies, run against synthetic candle data, confirmed to
  produce internally-consistent pending/live signals (verified the 2:1
  reward:risk math directly).
- The confluence/grading/backtest-weighted grading logic.
- The full risk-gate decision tree (kill switch, loss limits, cooldown,
  duplicate prevention, backtest-sample requirements) — 7 scenarios, all
  passing.
- The SQLite persistence layer — journal entries, closing trades, the
  auto-trade audit log — with a real database, not mocked.

The data connectors, broker adapter, and FastAPI routes are syntactically
verified and built against each service's real documented API, but you are
the first one to actually run them against live endpoints. Expect to find
and fix at least a few integration-level issues — that's normal for code
that's never touched the real network, not a sign something was done
carelessly.

## Known gaps

- No authentication on the API itself — add one before exposing this
  beyond localhost.
- Single-process, in-memory scheduler state (`SchedulerState`) — fine for
  one person running this for themselves, not for a multi-user deployment.
- The Deriv scan loop caps synthetic pairs at 10 per cycle to avoid
  hammering the WebSocket every minute; raise `[:10]` in
  `scheduler.py::run_scan_cycle` if you want full coverage and are
  confident your connection can handle it.
