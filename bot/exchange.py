"""Обёртка над pybit (Bybit V5 Unified) для торговых операций."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from pybit.exceptions import InvalidRequestError
from pybit.unified_trading import HTTP

from .parser import Direction

logger = logging.getLogger(__name__)

# Код ответа Bybit, когда плечо уже выставлено в нужное значение.
_LEVERAGE_NOT_MODIFIED = 110043


class ExchangeError(RuntimeError):
    """Ошибка при взаимодействии с Bybit."""


@dataclass(frozen=True)
class InstrumentInfo:
    qty_step: Decimal
    min_order_qty: Decimal
    tick_size: Decimal


@dataclass(frozen=True)
class OrderPlan:
    symbol: str
    side: str
    qty: Decimal
    entry_price: float
    stop_price: float
    take_profit: float


class BybitExchange:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        demo: bool = False,
    ) -> None:
        self.session = HTTP(
            api_key=api_key, api_secret=api_secret, testnet=testnet, demo=demo
        )
        self._instrument_cache: dict[str, InstrumentInfo] = {}

    def get_instrument_info(self, symbol: str) -> InstrumentInfo:
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]

        resp = self.session.get_instruments_info(category="linear", symbol=symbol)
        rows = resp.get("result", {}).get("list") or []
        if not rows:
            raise ExchangeError(f"Не найден инструмент {symbol} на Bybit")

        info = rows[0]
        lot = info["lotSizeFilter"]
        price = info["priceFilter"]
        instrument = InstrumentInfo(
            qty_step=Decimal(lot["qtyStep"]),
            min_order_qty=Decimal(lot["minOrderQty"]),
            tick_size=Decimal(price["tickSize"]),
        )
        self._instrument_cache[symbol] = instrument
        return instrument

    def get_last_price(self, symbol: str) -> float:
        resp = self.session.get_tickers(category="linear", symbol=symbol)
        rows = resp.get("result", {}).get("list") or []
        if not rows:
            raise ExchangeError(f"Не удалось получить цену для {symbol}")
        return float(rows[0]["lastPrice"])

    def has_open_position(self, symbol: str) -> bool:
        resp = self.session.get_positions(category="linear", symbol=symbol)
        rows = resp.get("result", {}).get("list") or []
        return any(float(r.get("size", "0")) > 0 for r in rows)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )
        except InvalidRequestError as exc:
            if exc.status_code == _LEVERAGE_NOT_MODIFIED:
                logger.debug("Плечо для %s уже равно %s", symbol, leverage)
                return
            raise ExchangeError(f"Не удалось выставить плечо для {symbol}: {exc}") from exc

    @staticmethod
    def _round_down(value: float, step: Decimal) -> Decimal:
        d = Decimal(str(value))
        return (d / step).to_integral_value(rounding=ROUND_DOWN) * step

    def build_order_plan(
        self,
        symbol: str,
        direction: Direction,
        order_size_usdt: float,
        leverage: int,
        stop_price: float,
        risk_reward: float,
    ) -> OrderPlan:
        instrument = self.get_instrument_info(symbol)
        entry_price = self.get_last_price(symbol)

        risk_per_unit = abs(entry_price - stop_price)
        if risk_per_unit <= 0:
            raise ExchangeError(
                f"Некорректный стоп для {symbol}: entry={entry_price}, stop={stop_price}"
            )

        if direction is Direction.LONG:
            side = "Buy"
            take_profit = entry_price + risk_per_unit * risk_reward
        else:
            side = "Sell"
            take_profit = entry_price - risk_per_unit * risk_reward

        raw_qty = (order_size_usdt * leverage) / entry_price
        qty = self._round_down(raw_qty, instrument.qty_step)

        if qty < instrument.min_order_qty:
            raise ExchangeError(
                f"Рассчитанный объём {qty} меньше минимального {instrument.min_order_qty} "
                f"для {symbol} (увеличьте ORDER_SIZE_USDT или плечо)"
            )

        take_profit = float(self._round_down(take_profit, instrument.tick_size))
        stop_price = float(self._round_down(stop_price, instrument.tick_size))

        return OrderPlan(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit=take_profit,
        )

    def open_position(self, plan: OrderPlan) -> dict:
        try:
            resp = self.session.place_order(
                category="linear",
                symbol=plan.symbol,
                side=plan.side,
                orderType="Market",
                qty=str(plan.qty),
                stopLoss=str(plan.stop_price),
                takeProfit=str(plan.take_profit),
                tpslMode="Full",
                slTriggerBy="LastPrice",
                tpTriggerBy="LastPrice",
                positionIdx=0,
            )
        except Exception as exc:
            raise ExchangeError(f"Не удалось открыть позицию по {plan.symbol}: {exc}") from exc

        logger.info("Ордер размещён: %s", resp)
        return resp
