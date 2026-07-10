"""Точка входа: связывает Telegram-слушатель, парсер сигналов и Bybit-обёртку."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from telethon.tl.custom.message import Message

from .config import Settings, load_settings
from .exchange import BybitExchange
from .listener import SignalListener
from .notifier import TelegramBotNotifier
from .parser import SignalParseError, parse_signal
from .stops import calculate_stop_price

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # httpx на уровне INFO логирует полный URL запроса, а в нём для Bot API
    # зашит секретный токен (https://api.telegram.org/bot<TOKEN>/...). Поднимаем
    # уровень, чтобы токен не утекал в логи контейнера.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def process_message(
    message: Message,
    settings: Settings,
    exchange: BybitExchange,
    notifier: TelegramBotNotifier,
) -> None:
    text = message.raw_text or ""
    logger.info("Новое сообщение: %r", text)

    if message.date is not None:
        age_seconds = time.time() - message.date.timestamp()
        if age_seconds > settings.max_signal_age_seconds:
            logger.warning("Сигнал слишком старый (%.0fс), пропуск: %r", age_seconds, text)
            return

    try:
        signal = parse_signal(text)
    except SignalParseError as exc:
        logger.info("Сообщение не является торговым сигналом: %s", exc)
        return

    logger.info("Сигнал: %s %s (%s)", signal.symbol, signal.direction.value, signal.pattern)

    if settings.entry_delay_candles > 0:
        delay_seconds = settings.entry_delay_candles * settings.stop_timeframe * 60
        logger.info(
            "Жду %s свечей (%sm) = %sс перед входом по %s",
            settings.entry_delay_candles, settings.stop_timeframe, delay_seconds, signal.symbol,
        )
        await notifier.send(
            f"⏳ Сигнал {signal.symbol} {signal.direction.value} (паттерн: {signal.pattern}) — "
            f"жду {settings.entry_delay_candles} свечей ({settings.stop_timeframe}m) перед входом, "
            "на случай отката."
        )
        await asyncio.sleep(delay_seconds)
        logger.info("Ожидание окончено, продолжаю обработку сигнала %s", signal.symbol)

    try:
        if exchange.has_open_position(signal.symbol):
            msg = f"⚠️ Пропущен сигнал {signal.symbol}: уже есть открытая позиция"
            logger.warning(msg)
            await notifier.send(msg)
            return

        stop_price = calculate_stop_price(
            exchange.session,
            signal.symbol,
            signal.direction,
            settings.stop_timeframe,
            settings.swing_window,
            settings.stop_lookback_candles,
            settings.stop_offset_pct,
        )

        plan = exchange.build_order_plan(
            signal.symbol,
            signal.direction,
            settings.order_size_usdt,
            settings.leverage,
            stop_price,
            settings.risk_reward,
        )

        logger.info(
            "План сделки: %s %s qty=%s entry~%.8f SL=%.8f TP=%.8f",
            plan.symbol, plan.side, plan.qty, plan.entry_price, plan.stop_price, plan.take_profit,
        )

        if settings.dry_run:
            await notifier.send(
                "🧪 DRY RUN — сделка не открыта\n"
                f"{plan.symbol} {plan.side} (паттерн: {signal.pattern})\n"
                f"qty={plan.qty} entry~{plan.entry_price} SL={plan.stop_price} "
                f"TP={plan.take_profit} (RR 1:{settings.risk_reward})"
            )
            return

        exchange.set_leverage(plan.symbol, settings.leverage)
        exchange.open_position(plan)

        await notifier.send(
            "✅ Открыта сделка\n"
            f"{plan.symbol} {plan.side} (паттерн: {signal.pattern})\n"
            f"qty={plan.qty}\nentry~{plan.entry_price}\nSL={plan.stop_price}\n"
            f"TP={plan.take_profit} (RR 1:{settings.risk_reward})"
        )

    except Exception as exc:  # noqa: BLE001 - хотим уведомить о любой ошибке и не падать
        logger.exception("Не удалось обработать сигнал %s", signal.symbol)
        await notifier.send(f"❌ Ошибка обработки сигнала {signal.symbol}: {exc}")


async def _async_main() -> None:
    settings = load_settings()
    _setup_logging(settings.log_level)

    Path(settings.tg_session_name).parent.mkdir(parents=True, exist_ok=True)

    exchange = BybitExchange(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
        testnet=settings.bybit_testnet,
        demo=settings.bybit_demo,
    )

    notifier = TelegramBotNotifier(
        bot_token=settings.notify_bot_token,
        chat_id=settings.notify_chat_id,
    )

    listener = SignalListener(
        session_name=settings.tg_session_name,
        api_id=settings.tg_api_id,
        api_hash=settings.tg_api_hash,
        source_chat=settings.tg_source_chat,
    )

    async def handler(message: Message) -> None:
        await process_message(message, settings, exchange, notifier)

    await listener.start()
    listener.register_handler(handler)

    bybit_mode = "TESTNET" if settings.bybit_testnet else "DEMO" if settings.bybit_demo else "LIVE"
    logger.info(
        "Бот запущен. BYBIT_MODE=%s, DRY_RUN=%s, ORDER_SIZE_USDT=%s, LEVERAGE=%s, RR=1:%s, "
        "STOP_TIMEFRAME=%sm, ENTRY_DELAY_CANDLES=%s",
        bybit_mode, settings.dry_run, settings.order_size_usdt, settings.leverage,
        settings.risk_reward, settings.stop_timeframe, settings.entry_delay_candles,
    )
    await notifier.send("🤖 Бот сигналов запущен и слушает канал")
    await listener.run_until_disconnected()


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
