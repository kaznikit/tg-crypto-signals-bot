"""Разбор текстовых сигналов из Telegram-канала.

Ожидаемый формат сообщения:
    Актив GRAMUSDT, паттерн `Двойная вершина`

Паттерн может быть в обратных кавычках или без них, регистр не важен,
вокруг запятой/слов возможны лишние пробелы.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


# Паттерн -> направление сделки. Ключи в нижнем регистре без кавычек.
PATTERN_DIRECTIONS: dict[str, Direction] = {
    "двойная вершина": Direction.SHORT,
    "двойное дно": Direction.LONG,
}

_ASSET_RE = re.compile(r"актив\s*[:\-]?\s*([A-Za-z0-9]+)", re.IGNORECASE)
_PATTERN_RE = re.compile(r"паттерн\s*[:\-]?\s*`?([^`\n,]+?)`?\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class Signal:
    symbol: str
    pattern: str
    direction: Direction
    raw_text: str


class SignalParseError(ValueError):
    """Сообщение не удалось разобрать или паттерн не поддерживается."""


def _normalize_symbol(raw_symbol: str) -> str:
    symbol = raw_symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"
    return symbol


def parse_signal(text: str) -> Signal:
    """Разбирает текст сообщения в Signal. Бросает SignalParseError, если
    сообщение не похоже на сигнал или паттерн неизвестен/не торгуемый."""
    if not text:
        raise SignalParseError("Пустое сообщение")

    asset_match = _ASSET_RE.search(text)
    pattern_match = _PATTERN_RE.search(text)

    if not asset_match or not pattern_match:
        raise SignalParseError(f"Не найден актив и/или паттерн в сообщении: {text!r}")

    symbol = _normalize_symbol(asset_match.group(1))
    pattern_raw = pattern_match.group(1).strip().strip("`").strip()
    pattern_key = pattern_raw.lower()

    direction = PATTERN_DIRECTIONS.get(pattern_key)
    if direction is None:
        raise SignalParseError(
            f"Паттерн {pattern_raw!r} не поддерживается (нет маппинга на направление)"
        )

    return Signal(symbol=symbol, pattern=pattern_raw, direction=direction, raw_text=text)
