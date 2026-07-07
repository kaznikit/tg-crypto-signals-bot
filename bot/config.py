"""Конфигурация бота, читается из переменных окружения / .env файла."""
from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram user account (Telethon)
    tg_api_id: int = Field(..., alias="TG_API_ID")
    tg_api_hash: str = Field(..., alias="TG_API_HASH")
    tg_source_chat: str = Field(..., alias="TG_SOURCE_CHAT")
    tg_session_name: str = Field("session/user", alias="TG_SESSION_NAME")

    # Уведомления о сделках (отдельный Telegram-канал через Bot API)
    notify_bot_token: str = Field(..., alias="NOTIFY_BOT_TOKEN")
    notify_chat_id: str = Field(..., alias="NOTIFY_CHAT_ID")

    # Bybit
    bybit_api_key: str = Field(..., alias="BYBIT_API_KEY")
    bybit_api_secret: str = Field(..., alias="BYBIT_API_SECRET")
    bybit_testnet: bool = Field(False, alias="BYBIT_TESTNET")
    # Demo Trading — паралелльный "бумажный" аккаунт на mainnet с реальными
    # котировками, но виртуальным балансом. Нужны отдельные API-ключи,
    # выпущенные в разделе Demo Trading личного кабинета Bybit.
    bybit_demo: bool = Field(False, alias="BYBIT_DEMO")

    # Trading params
    order_size_usdt: float = Field(50.0, alias="ORDER_SIZE_USDT")
    leverage: int = Field(5, alias="LEVERAGE")
    risk_reward: float = Field(2.0, alias="RISK_REWARD")
    stop_timeframe: int = Field(5, alias="STOP_TIMEFRAME")
    stop_offset_pct: float = Field(0.05, alias="STOP_OFFSET_PCT")
    swing_window: int = Field(2, alias="SWING_WINDOW")
    stop_lookback_candles: int = Field(200, alias="STOP_LOOKBACK_CANDLES")
    max_signal_age_seconds: int = Field(120, alias="MAX_SIGNAL_AGE_SECONDS")

    dry_run: bool = Field(False, alias="DRY_RUN")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("stop_timeframe")
    @classmethod
    def _validate_timeframe(cls, v: int) -> int:
        if v not in (5, 15):
            raise ValueError("STOP_TIMEFRAME должен быть 5 или 15")
        return v

    @model_validator(mode="after")
    def _validate_bybit_mode(self) -> "Settings":
        if self.bybit_testnet and self.bybit_demo:
            raise ValueError("BYBIT_TESTNET и BYBIT_DEMO нельзя включать одновременно")
        return self


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
