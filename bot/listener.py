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

    async def _resolve_entity(self):
        """Пытается найти чат по username/ID. Если TG_SOURCE_CHAT оказался
        просто отображаемым названием канала (например, скопированным из
        шапки чата) — ищет точное совпадение по названию среди диалогов,
        в которых уже состоит аккаунт."""
        try:
            return await self.client.get_entity(self._source_chat_ref)
        except (ValueError, TypeError) as exc:
            if isinstance(self._source_chat_ref, int):
                raise

            title = str(self._source_chat_ref).strip()
            matches = []
            async for dialog in self.client.iter_dialogs():
                if dialog.name and dialog.name.strip() == title:
                    matches.append(dialog)

            if len(matches) == 1:
                dialog = matches[0]
                logger.warning(
                    "TG_SOURCE_CHAT=%r похоже на название чата, а не username/ID. "
                    "Нашёл по названию среди ваших диалогов (id=%s). Рекомендуется "
                    "указать в .env числовой ID (запустите `python -m bot.list_chats`), "
                    "т.к. название канала может измениться.",
                    title, dialog.id,
                )
                return dialog.entity

            if len(matches) > 1:
                raise ValueError(
                    f"Найдено {len(matches)} чатов с названием {title!r} — уточните "
                    "TG_SOURCE_CHAT числовым ID. Запустите `python -m bot.list_chats`, "
                    "чтобы посмотреть ID всех ваших чатов."
                ) from exc

            raise ValueError(
                f"Не удалось найти чат {title!r} ни как username/ID, ни по точному "
                "названию среди ваших диалогов. Проверьте значение TG_SOURCE_CHAT: "
                "укажите @username канала (без @) или его числовой ID. Чтобы посмотреть "
                "список всех ваших чатов с ID, запустите `python -m bot.list_chats`."
            ) from exc

    async def start(self) -> None:
        """Подключается и авторизуется. При первом запуске без сохранённой
        сессии Telethon запросит номер телефона и код подтверждения в консоли."""
        await self.client.start()
        self._entity = await self._resolve_entity()
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
