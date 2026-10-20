
"""Conservative SPY paper-trading execution engine."""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    OrderSide,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

SYMBOL = "SPY"
START_CAPITAL = Decimal("50")
MAX_POSITION = Decimal("10")
DAILY_LOSS_LIMIT = Decimal("2")
TOTAL_LOSS_LIMIT = Decimal("10")
CASH_BUFFER = Decimal("1")
FAST = 5
SLOW = 20

EASTERN = ZoneInfo("America/New_York")


def dec(value):
    return Decimal(str(value))


def report(message, *args):
    logging.info("DECISION: " + message, *args)


def run():
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    expected_id = os.environ["EXPECTED_PAPER_ACCOUNT_ID"].strip()

    # Default is dry-run. Submission requires explicit confirmation.
    execute = os.environ.get("EXECUTE_PAPER_ORDERS") == "true"
    confirmation = os.environ.get("CONFIRM_PAPER_EXECUTION") == (
        "I_UNDERSTAND_PAPER_ORDERS"
    )

    trading = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)

    account = trading.get_account()

    if not expected_id or str(account.id) != expected_id:
        raise RuntimeError("Paper account verification failed")

    if account.trading_blocked or account.account_blocked:
        report("HALT: account blocked")
        return

    equity = dec(account.equity)
    previous = dec(account.last_equity)
    cash = dec(account.cash)

    logging.info(
        "MODE=%s equity=%s cash=%s",
        "PAPER_EXECUTION" if execute else "DRY_RUN",
        equity,
        cash,
    )

    if execute and not confirmation:
        raise RuntimeError("Paper execution confirmation missing")

    daily_drawdown = max(Decimal("0"), previous - equity)
    total_drawdown = max(Decimal("0"), START_CAPITAL - equity)

    logging.info(
        "RISK: daily=%s/%s total=%s/%s",
        daily_drawdown,
        DAILY_LOSS_LIMIT,
        total_drawdown,
        TOTAL_LOSS_LIMIT,
    )

    if (
        daily_drawdown >= DAILY_LOSS_LIMIT
        or total_drawdown >= TOTAL_LOSS_LIMIT
    ):
        report("HALT: loss threshold reached")
        return

    positions = trading.get_all_positions()

    if any(p.symbol != SYMBOL for p in positions):
        report("HALT: unexpected holdings")
        return

    position = next(
        (p for p in positions if p.symbol == SYMBOL),
        None,
    )

    if position and dec(position.qty) <= 0:
        report("HALT: invalid or short position")
        return

    open_orders = trading.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.OPEN
        )
    )

    if open_orders:
        report("WAIT: existing open order detected")
        return

    clock = trading.get_clock()

    if not clock.is_open:
        report("WAIT: market closed")
        return

    now = datetime.now(timezone.utc)
    today_et = now.astimezone(EASTERN).date()

    bars = data.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=SYMBOL,
            timeframe=TimeFrame.Day,
            start=now - timedelta(days=90),
            end=now,
            feed="iex",
        )
    ).data.get(SYMBOL, [])

    completed = sorted(
        (
            bar
            for bar in bars
            if bar.timestamp.astimezone(EASTERN).date()
            < today_et
        ),
        key=lambda bar: bar.timestamp,
    )

    closes = [dec(bar.close) for bar in completed]

    if len(closes) < SLOW:
        report("HALT: insufficient historical data")
        return

    fast_ma = sum(closes[-FAST:]) / FAST
    slow_ma = sum(closes[-SLOW:]) / SLOW

    logging.info(
        "SIGNAL: SPY MA(5)=%s MA(20)=%s",
        fast_ma,
        slow_ma,
    )

    order = None

    if fast_ma <= slow_ma:
        if not position:
            report("STAY_CASH: bearish trend")
            return

        # Sell only the existing SPY shares.
        qty = dec(position.qty).quantize(
            Decimal("0.000000001"),
            rounding=ROUND_DOWN,
        )

        if qty <= 0:
            report("HALT: invalid sell quantity")
            return

        report("SELL: %s shares of SPY", qty)

        order = MarketOrderRequest(
            symbol=SYMBOL,
            qty=float(qty),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )

    else:
        if position:
            report("HOLD: existing SPY position")
            return

        budget = min(
            MAX_POSITION,
            cash - CASH_BUFFER,
        )

        budget = budget.quantize(
            Decimal("0.01"),
            rounding=ROUND_DOWN,
        )

        if budget < Decimal("1"):
            report("STAY_CASH: insufficient cash")
            return

        report("BUY: SPY notional=%s", budget)

        order = MarketOrderRequest(
            symbol=SYMBOL,
            notional=float(budget),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )

    if not execute:
        report("DRY_RUN: order prepared but not submitted")
        return

    # Recheck market and open orders immediately before submission.
    if not trading.get_clock().is_open:
        report("WAIT: market closed before submission")
        return

    if trading.get_orders(
        filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)
    ):
        report("WAIT: new open order detected")
        return

    submitted = trading.submit_order(order_data=order)

    logging.info(
        "PAPER ORDER SUBMITTED: id=%s status=%s",
        submitted.id,
        submitted.status,
    )


if __name__ == "__main__":
    run()
