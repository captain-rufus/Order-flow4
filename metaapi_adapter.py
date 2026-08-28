"""
MetaApi broker adapter -- real MT4/MT5 execution via MetaApi.cloud's
official Python SDK (metaapi-cloud-sdk). Built against their documented
API shape, verified via their published docs before writing this -- NOT
against a live test account, since none is available here.

=============================================================================
READ BEFORE ENABLING REAL EXECUTION:

1. This has NEVER run against a real or demo MetaApi account. It's written
   correctly against MetaApi's documented SDK patterns, but "correctly
   written" and "verified working" are different things with real money.

2. DRY_RUN defaults to True. Every method below logs exactly what it WOULD
   have done and returns a synthetic response, without calling MetaApi at
   all, while DRY_RUN=True.

3. Before ever setting DRY_RUN=False: connect to a MetaApi DEMO account
   (not live), watch it place and manage trades there for weeks across
   varied conditions, confirm position sizing/SL/TP match what you'd
   expect by hand. Only move to live after that, starting with the
   smallest risk_per_trade_pct you're willing to be wrong about.

4. Your MetaApi token is read from an environment variable
   (METAAPI_TOKEN), never hardcoded, never logged, never sent to the
   frontend -- same token-based (not password-based) pattern as the
   browser tool's Auto-Trading config panel.
=============================================================================
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    message: str = ""
    dry_run: bool = False


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float


class MetaApiAdapter:
    def __init__(self, token: str, account_id: str, dry_run: bool = True):
        self.token = token
        self.account_id = account_id
        self.dry_run = dry_run
        self._api = None
        self._account = None
        self._connection = None

    async def connect(self):
        if self.dry_run:
            logger.info("[DRY RUN] Would connect to MetaApi account %s", self.account_id)
            return
        try:
            from metaapi_cloud_sdk import MetaApi
        except ImportError as e:
            raise RuntimeError("metaapi-cloud-sdk is not installed. Run: pip install metaapi-cloud-sdk") from e

        self._api = MetaApi(self.token)
        self._account = await self._api.metatrader_account_api.get_account(self.account_id)
        if self._account.state not in ("DEPLOYED",):
            logger.info("Deploying MetaApi account %s...", self.account_id)
            await self._account.deploy()
        await self._account.wait_connected()
        self._connection = self._account.get_rpc_connection()
        await self._connection.connect()
        await self._connection.wait_synchronized()
        logger.info("Connected to MetaApi account %s", self.account_id)

    async def get_account_info(self) -> AccountInfo:
        if self.dry_run:
            logger.info("[DRY RUN] Returning placeholder account info (not real)")
            return AccountInfo(balance=0.0, equity=0.0, margin=0.0, free_margin=0.0)
        info = await self._connection.get_account_information()
        return AccountInfo(balance=info["balance"], equity=info["equity"],
                           margin=info["margin"], free_margin=info["freeMargin"])

    async def get_symbol_specification(self, symbol: str) -> dict:
        if self.dry_run:
            logger.info("[DRY RUN] Returning placeholder symbol spec for %s", symbol)
            return {"contractSize": 100000, "volumeStep": 0.01, "minVolume": 0.01, "maxVolume": 100}
        return await self._connection.get_symbol_specification(symbol)

    async def place_market_order(self, symbol: str, direction: str, volume: float,
                                  stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                                  comment: str = "orderflow-auto") -> OrderResult:
        if self.dry_run:
            logger.info("[DRY RUN] Would place %s %s x%s (SL=%s TP=%s) — NOT sent to any broker",
                        direction, symbol, volume, stop_loss, take_profit)
            return OrderResult(success=True, order_id="DRYRUN", position_id="DRYRUN",
                               message="Dry run — no real order placed.", dry_run=True)
        try:
            if direction == "BUY":
                result = await self._connection.create_market_buy_order(
                    symbol=symbol, volume=volume, stop_loss=stop_loss, take_profit=take_profit,
                    options={"comment": comment})
            else:
                result = await self._connection.create_market_sell_order(
                    symbol=symbol, volume=volume, stop_loss=stop_loss, take_profit=take_profit,
                    options={"comment": comment})
            return OrderResult(success=True, order_id=str(result.get("orderId")),
                               position_id=str(result.get("positionId")),
                               message=result.get("stringCode", "TRADE_RETCODE_DONE"))
        except Exception as err:
            logger.exception("MetaApi order placement failed for %s %s", direction, symbol)
            return OrderResult(success=False, message=str(err))

    async def close_position(self, position_id: str) -> OrderResult:
        if self.dry_run:
            logger.info("[DRY RUN] Would close position %s — not sent to any broker", position_id)
            return OrderResult(success=True, position_id=position_id, dry_run=True, message="Dry run.")
        try:
            result = await self._connection.close_position(position_id)
            return OrderResult(success=True, position_id=position_id,
                               message=result.get("stringCode", "TRADE_RETCODE_DONE"))
        except Exception as err:
            logger.exception("MetaApi close_position failed for %s", position_id)
            return OrderResult(success=False, message=str(err))

    async def close_all_positions(self) -> list[OrderResult]:
        if self.dry_run:
            logger.info("[DRY RUN] Would close ALL open positions — not sent to any broker")
            return [OrderResult(success=True, dry_run=True, message="Dry run.")]
        try:
            positions = await self._connection.get_positions()
        except Exception as err:
            logger.exception("Failed to fetch open positions for close-all")
            return [OrderResult(success=False, message=str(err))]
        return [await self.close_position(pos["id"]) for pos in positions]

    async def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                               take_profit: Optional[float] = None) -> OrderResult:
        if self.dry_run:
            logger.info("[DRY RUN] Would modify position %s (SL=%s TP=%s) — not sent to any broker",
                        position_id, stop_loss, take_profit)
            return OrderResult(success=True, position_id=position_id, dry_run=True, message="Dry run.")
        try:
            result = await self._connection.modify_position(position_id, stop_loss=stop_loss, take_profit=take_profit)
            return OrderResult(success=True, position_id=position_id,
                               message=result.get("stringCode", "TRADE_RETCODE_DONE"))
        except Exception as err:
            logger.exception("MetaApi modify_position failed for %s", position_id)
            return OrderResult(success=False, message=str(err))
