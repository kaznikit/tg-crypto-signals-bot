"""Расчёт стоп-лосса по ближайшему свинг-экстремуму на 5m/15m свечах Bybit."""
from __future__ import annotations

import logging

from pybit.unified_trading import HTTP

from .parser import Direction

logger = logging.getLogger(__name__)


class StopCalculationError(RuntimeError):
    """Не удалось определить свинг-экстремум для стопа."""


def _fetch_closed_candles(session: HTTP, symbol: str, timeframe: int, limit: int) -> list[dict]:
    """Возвращает закрытые свечи от старых к новым (без текущей формирующейся)."""
    resp = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=str(timeframe),
        limit=min(limit + 1, 1000),
    )
    rows = resp.get("result", {}).get("list") or []
    if not rows:
        raise StopCalculationError(f"Bybit не вернул свечи для {symbol}")

    # Bybit отдаёт свечи от новых к старым; первая (list[0]) обычно ещё не закрыта.
    closed = list(rows[1:])
    closed.reverse()  # от старых к новым

    return [
        {"start": int(r[0]), "high": float(r[2]), "low": float(r[3])}
        for r in closed
    ]


def _find_last_swing_high(candles: list[dict], window: int) -> float | None:
    n = len(candles)
    for i in range(n - 1 - window, window - 1, -1):
        pivot = candles[i]["high"]
        left = candles[i - window:i]
        right = candles[i + 1:i + 1 + window]
        if all(pivot > c["high"] for c in left) and all(pivot > c["high"] for c in right):
            return pivot
    return None


def _find_last_swing_low(candles: list[dict], window: int) -> float | None:
    n = len(candles)
    for i in range(n - 1 - window, window - 1, -1):
        pivot = candles[i]["low"]
        left = candles[i - window:i]
        right = candles[i + 1:i + 1 + window]
        if all(pivot < c["low"] for c in left) and all(pivot < c["low"] for c in right):
            return pivot
    return None


def calculate_stop_price(
    session: HTTP,
    symbol: str,
    direction: Direction,
    timeframe: int,
    swing_window: int,
    lookback_candles: int,
    offset_pct: float,
) -> float:
    """Ищет последний (ближайший по времени) свинг-экстремум на закрытых свечах
    и возвращает цену стопа с отступом offset_pct (%) за экстремумом."""
    candles = _fetch_closed_candles(session, symbol, timeframe, lookback_candles)

    if len(candles) < 2 * swing_window + 1:
        raise StopCalculationError(
            f"Недостаточно свечей для {symbol} ({len(candles)}) при окне {swing_window}"
        )

    if direction is Direction.SHORT:
        extreme = _find_last_swing_high(candles, swing_window)
        if extreme is None:
            raise StopCalculationError(
                f"Не найден свинг-хай для {symbol} на {timeframe}m (окно {swing_window})"
            )
        stop_price = extreme * (1 + offset_pct / 100)
    else:
        extreme = _find_last_swing_low(candles, swing_window)
        if extreme is None:
            raise StopCalculationError(
                f"Не найден свинг-лоу для {symbol} на {timeframe}m (окно {swing_window})"
            )
        stop_price = extreme * (1 - offset_pct / 100)

    logger.info(
        "Стоп для %s (%s, %sm): экстремум=%.8f, стоп=%.8f",
        symbol, direction.value, timeframe, extreme, stop_price,
    )
    return stop_price
