"""Отправка уведомлений о сделках в отдельный Telegram-канал через Bot API."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"


class NotifierError(RuntimeError):
    """Не удалось отправить уведомление через Telegram Bot API."""


class TelegramBotNotifier:
    """Простой клиент Bot API для публикации сообщений о сделках.

    Отдельный от Telethon-сессии бот: тому нужен только токен от @BotFather
    и право писать в целевой чат/канал (для канала — быть в нём администратором).
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._url = f"{_API_BASE}/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self._url,
                    json={"chat_id": self._chat_id, "text": text},
                )
            data = resp.json()
            if not data.get("ok"):
                logger.error("Telegram Bot API вернул ошибку при отправке уведомления: %s", data)
        except Exception as exc:
            logger.error("Не удалось отправить уведомление в Telegram-канал: %s", self._redact(exc))

    def _redact(self, exc: Exception) -> str:
        """Убирает URL (с зашитым токеном бота) из текста ошибки перед логированием."""
        return str(exc).replace(self._url, "https://api.telegram.org/bot<redacted>/sendMessage")
