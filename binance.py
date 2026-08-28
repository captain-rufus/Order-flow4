"""Binance public REST API -- crypto candles. No key required."""
from __future__ import annotations
import asyncio
import httpx
from app.models import Candle, CandleSet, Timeframe

BINANCE_INTERVALS = {
    Timeframe.D1: "1d", Timeframe.H4: "4h", Timeframe.H1: "1h",
    Timeframe.M15: "15m", Timeframe.M5: "5m",
}


async def fetch_binance_candles(symbol: str, tf: Timeframe, limit: int = 180) -> list[Candle]:
    interval = BINANCE_INTERVALS[tf]
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url)
        res.raise_for_status()
        data = res.json()
    return [Candle(time=k[0], open=float(k[1]), high=float(k[2]), low=float(k[3]), close=float(k[4])) for k in data]


async def load_crypto_data(symbol: str) -> CandleSet:
    tasks = {tf: fetch_binance_candles(symbol, tf) for tf in Timeframe}
    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))


async def fetch_latest_price(symbol: str) -> float | None:
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return None
            return float(res.json()["price"])
    except Exception:
        return None
