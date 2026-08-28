"""Deriv public WebSocket API -- synthetic indices. Symbol codes pulled live
from Deriv's own active_symbols registry, not guessed."""
from __future__ import annotations
import asyncio
import itertools
import json
from typing import Optional
import websockets
from app.models import Candle, CandleSet, Timeframe

DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"
DERIV_GRANULARITY = {
    Timeframe.D1: 86400, Timeframe.H4: 14400, Timeframe.H1: 3600,
    Timeframe.M15: 900, Timeframe.M5: 300,
}


class DerivClient:
    def __init__(self):
        self._ws = None
        self._req_id_counter = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._symbol_map: dict[str, str] = {}
        self._listener_task = None
        self._lock = asyncio.Lock()

    async def connect(self):
        async with self._lock:
            if self._ws is not None and not self._ws.closed:
                return
            self._ws = await websockets.connect(DERIV_WS_URL, ping_interval=20, ping_timeout=20)
            self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            async for raw in self._ws:
                data = json.loads(raw)
                req_id = data.get("req_id")
                if req_id is not None and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        if data.get("error"):
                            fut.set_exception(RuntimeError(data["error"].get("message", "Deriv API error")))
                        else:
                            fut.set_result(data)
        except websockets.ConnectionClosed:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("Deriv connection closed"))
            self._pending.clear()

    async def send(self, request: dict, timeout: float = 10.0) -> dict:
        if self._ws is None or self._ws.closed:
            await self.connect()
        req_id = next(self._req_id_counter)
        fut = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        await self._ws.send(json.dumps({**request, "req_id": req_id}))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError("Deriv request timed out")

    @property
    def known_symbols(self) -> list[str]:
        return sorted(self._symbol_map.keys())

    async def load_symbol_list(self) -> list[str]:
        res = await self.send({"active_symbols": "brief", "product_type": "basic"})
        symbols = [s for s in res.get("active_symbols", []) if s.get("market") == "synthetic_index"]
        self._symbol_map = {s["display_name"]: s["symbol"] for s in symbols}
        return sorted(self._symbol_map.keys())

    async def fetch_candles(self, display_name: str, tf: Timeframe, count: int = 180) -> list[Candle]:
        symbol = self._symbol_map.get(display_name)
        if not symbol:
            raise ValueError(f'No Deriv symbol code found for "{display_name}"')
        res = await self.send({
            "ticks_history": symbol, "style": "candles",
            "granularity": DERIV_GRANULARITY[tf], "count": count, "end": "latest",
        })
        candles = res.get("candles", [])
        return [Candle(time=c["epoch"] * 1000, open=float(c["open"]), high=float(c["high"]),
                        low=float(c["low"]), close=float(c["close"])) for c in candles]

    async def fetch_latest_price(self, display_name: str) -> Optional[float]:
        symbol = self._symbol_map.get(display_name)
        if not symbol:
            return None
        try:
            res = await self.send({"ticks_history": symbol, "style": "ticks", "count": 1, "end": "latest"})
            prices = (res.get("history") or {}).get("prices")
            return float(prices[-1]) if prices else None
        except Exception:
            return None

    async def load_all_timeframes(self, display_name: str) -> CandleSet:
        results = await asyncio.gather(*(self.fetch_candles(display_name, tf) for tf in Timeframe))
        return dict(zip(Timeframe, results))


deriv_client = DerivClient()
