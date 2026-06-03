from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppSettings:
    database_url: str
    sec_user_agent: str | None
    futu_host: str
    futu_port: int
    futu_market: str
    minimax_base_url: str
    minimax_model: str
    minimax_api: str
    minimax_api_key: str | None
    minimax_retries: int
    minimax_retry_wait_seconds: float


def load_settings() -> AppSettings:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    return AppSettings(
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://joeyang@localhost:5432/hidden_champion_screener",
        ),
        sec_user_agent=os.environ.get("SEC_USER_AGENT"),
        futu_host=os.environ.get("FUTU_HOST", "127.0.0.1"),
        futu_port=int(os.environ.get("FUTU_PORT", "11111")),
        futu_market=os.environ.get("FUTU_MARKET", "US"),
        minimax_base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic/v1"),
        minimax_model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
        minimax_api=os.environ.get("MINIMAX_API", "anthropic-messages"),
        minimax_api_key=os.environ.get("MINIMAX_API_KEY") or None,
        minimax_retries=int(os.environ.get("MINIMAX_RETRIES", "1")),
        minimax_retry_wait_seconds=float(os.environ.get("MINIMAX_RETRY_WAIT_SECONDS", "30")),
    )
