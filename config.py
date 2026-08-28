"""Environment-based settings. Nothing secret has a default value baked in --
tokens must come from the environment or the app refuses to start real execution."""
from __future__ import annotations
import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Safety-critical: defaults to True. Only real execution if explicitly
    # set to false AND a valid MetaApi token/account are configured.
    dry_run: bool = _bool_env("DRY_RUN", True)
    auto_trade_master_switch: bool = _bool_env("AUTO_TRADE_ENABLED", False)

    metaapi_token: str = os.environ.get("METAAPI_TOKEN", "")
    metaapi_account_id: str = os.environ.get("METAAPI_ACCOUNT_ID", "")

    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")
    discord_webhook_url: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

    database_path: str = os.environ.get("DATABASE_PATH", "orderflow.db")
    scan_interval_seconds: int = int(os.environ.get("SCAN_INTERVAL_SECONDS", "60"))

    crypto_pairs: tuple = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT")


settings = Settings()
