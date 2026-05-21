from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_id: int
    database_url: str
    tz_name: str
    port: int
    public_url: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


def load_settings() -> Settings:
    return Settings(
        bot_token=_require("BOT_TOKEN"),
        owner_id=int(_require("OWNER_ID")),
        database_url=_require("DATABASE_URL"),
        tz_name=os.getenv("TZ", "Europe/Moscow"),
        port=int(os.getenv("PORT", "8080")),
        public_url=os.getenv("PUBLIC_URL", ""),
    )
