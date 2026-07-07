"""Утилита: печатает список ваших диалогов (каналы/группы/чаты) с ID и username.

Помогает найти правильное значение для TG_SOURCE_CHAT в .env, если у канала
нет публичного @username или вы не уверены в его точном названии.

Запуск (из корня проекта, после того как заполнены TG_API_ID/TG_API_HASH):

    python -m bot.list_chats [подстрока для фильтра]

Пример:

    python -m bot.list_chats morzh

При первом запуске потребует авторизацию Telegram (как и основной бот).
Работает на ВРЕМЕННОЙ КОПИИ файла сессии TG_SESSION_NAME (если он уже
существует), чтобы не конфликтовать за блокировку SQLite с уже запущенным
основным ботом (иначе оба процесса могут упасть с "database is locked").
Повторно вводить код подтверждения при этом не придётся — копия сессии
уже авторизована.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient


async def _main() -> None:
    load_dotenv()

    try:
        api_id = int(os.environ["TG_API_ID"])
        api_hash = os.environ["TG_API_HASH"]
    except KeyError as exc:
        raise SystemExit(
            f"В .env не задана переменная {exc.args[0]}. Заполните TG_API_ID и TG_API_HASH."
        ) from exc

    session_name = os.environ.get("TG_SESSION_NAME", "session/user")
    session_dir = os.path.dirname(session_name)
    if session_dir:
        os.makedirs(session_dir, exist_ok=True)

    query = sys.argv[1].lower() if len(sys.argv) > 1 else None

    # Если основной бот уже запущен и использует тот же файл сессии, открывать
    # его вторым процессом напрямую нельзя — SQLite отдаст "database is locked"
    # и может уронить основной бот. Поэтому работаем на отдельной копии.
    original_session_file = Path(f"{session_name}.session")
    temp_session_name = f"{session_name}_list_chats_tmp"
    temp_session_file = Path(f"{temp_session_name}.session")

    session_to_use = session_name
    using_temp_copy = False
    if original_session_file.exists():
        shutil.copyfile(original_session_file, temp_session_file)
        session_to_use = temp_session_name
        using_temp_copy = True

    client = TelegramClient(session_to_use, api_id, api_hash)
    try:
        await client.start()

        print(f"{'ID':<16} {'Username':<25} Название")
        print("-" * 70)
        async for dialog in client.iter_dialogs():
            if query and query not in (dialog.name or "").lower():
                continue
            username = getattr(dialog.entity, "username", None)
            username_str = f"@{username}" if username else "-"
            print(f"{dialog.id:<16} {username_str:<25} {dialog.name}")

        await client.disconnect()
    finally:
        if using_temp_copy:
            temp_session_file.unlink(missing_ok=True)
            Path(f"{temp_session_name}.session-journal").unlink(missing_ok=True)

    print(
        "\nВ TG_SOURCE_CHAT укажите Username (без @) если он есть, иначе — ID из левого столбца."
    )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
