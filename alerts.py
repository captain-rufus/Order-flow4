"""Telegram/Discord alerting -- fires for A+ signals and for auto-trade
executions/blocks, sent server-side so it works even with no browser open."""
from __future__ import annotations
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def send_telegram(text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json={"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "Markdown"})
            return res.status_code == 200
    except Exception:
        logger.exception("Telegram alert failed")
        return False


async def send_discord(text: str) -> bool:
    if not settings.discord_webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(settings.discord_webhook_url, json={"content": text})
            return res.status_code in (200, 204)
    except Exception:
        logger.exception("Discord alert failed")
        return False


async def notify(text: str) -> None:
    """Fire-and-forget to both channels; failures are logged, never raised."""
    await send_telegram(text)
    await send_discord(text)


def format_signal_alert(pair: str, signal) -> str:
    return (f"*{signal.grade_label} Signal — {pair}*\n"
            f"{signal.direction.value} via {signal.strategy.replace('_', ' ')}\n"
            f"Confidence: {signal.confidence}% · R:R {signal.rr}:1\n"
            f"Entry: {signal.entry} · Stop: {signal.stop}\n{signal.reason}")


def format_autotrade_alert(pair: str, action: str, reason: str, dry_run: bool) -> str:
    prefix = "[DRY RUN] " if dry_run else ""
    return f"{prefix}Auto-trade {action} on {pair}: {reason}"
