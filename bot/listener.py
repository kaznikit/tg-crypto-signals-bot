"""Telethon-клиент: слушает канал с сигналами и передаёт сообщения в обработчик.

Канал не принадлежит нам, поэтому используется пользовательская сессия
Telegram (не Bot API) — бот "видит" сообщения так же, как обычный участник/
подписчик канала.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from telethon import TelegramClient, events
from telethon.tl.custom.message import Message

logger = logging.getLogger(__name__)

MessageHandler = Callable[[Message], Awaitable[None]]


def _resolve_chat(value: str) -> int | str:
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        return value.lstrip("@")


class SignalListener:
    def __init__(self, session_name: str, api_id: int, api_hash: str, source_chat: str) -> None:
        self.client = TelegramClient(session_name, api_id, api_hash)
        self._source_chat_ref = _resolve_chat(source_chat)
        self._entity = None

    async def start(self) -> None:
        """Подключается и авторизуется. При первом запуске без сохранённой
        сессии Telethon запросит номер телефона и код подтверждения в консоли."""
        await self.client.start()
        self._entity = await self.client.get_entity(self._source_chat_ref)
        me = await self.client.get_me()
        logger.info(
            "Telegram-клиент запущен как %s, слушаю канал %r",
            getattr(me, "username", None) or me.id,
            self._source_chat_ref,
        )

    def register_handler(self, handler: MessageHandler) -> None:
        if self._entity is None:
            raise RuntimeError("Сначала вызовите start(), чтобы определить канал")

        @self.client.on(events.NewMessage(chats=self._entity))
        async def _on_message(event: events.NewMessage.Event) -> None:
            try:
                await handler(event.message)
            except Exception:
                logger.exception("Ошибка обработки входящего сообщения")

    async def run_until_disconnected(self) -> None:
        await self.client.run_until_disconnected()
