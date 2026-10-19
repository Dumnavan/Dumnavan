
"""Read-only Alpaca paper-account SPY strategy with conservative risk checks."""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

SYMBOL = "SPY"
START_CAPITAL = Decimal("50")
MAX_POSITION = Decimal("10")
DAILY_LOSS = Decimal("2")
TOTAL_LOSS = Decimal("10")
MIN_CASH_BUFFER = Decimal("1")

FAST = 5
SLOW = 20

EASTERN = ZoneInfo("America/New_York")


def money(value):
    return Decimal(str(value))


def decision(message, *args):
    logging.info("DECISION: " + message, *args)


def run():
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]

    # Connect exclusively to Alpaca paper trading
    trading = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)

    account = trading.get_account()

    # Optional account identity verification
    expected_id = os.environ.get(
        "EXPECTED_PAPER_ACCOUNT_ID", ""
    ).strip()

    if not expected_id:
    raise RuntimeError(
        "EXPECTED_PAPER_ACCOUNT_ID is missing"
    )

if str(account.id) != expected_id:
        raise RuntimeError(
            "Unexpected paper account ID; no action taken"
        )

    equity = money(account.equity)
    previous_equity = money(account.last_equity)
    cash = money(account.cash)

    logging.info(
        "MODE=READ_ONLY SYMBOL=%s equity=%s cash=%s previous_equity=%s",
        SYMBOL,
        equity,
        cash,
        previous_equity
    )

    # Check account restrictions
    if account.trading_blocked or account.account_blocked:
        decision("HALT: account blocked")
        return

    # Check existing positions and open orders
    positions = trading.get_all_positions()

    open_orders = trading.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.OPEN
        )
    )

    if any(p.symbol != SYMBOL for p in positions):
        decision("HALT: unexpected holdings present")
        return

    if open_orders:
        decision(
            "WAIT: %s open order(s) present",
            len(open_orders)
        )
        return

    position = next(
        (p for p in positions if p.symbol == SYMBOL),
        None
    )

    position_value = (
        abs(money(position.market_value))
        if position
        else Decimal("0")
    )

    # Reject short positions
    if position and money(position.qty) < 0:
        decision("HALT: short SPY position detected")
        return

    # Enforce maximum position value
    if position_value > MAX_POSITION:
        decision(
            "HALT: SPY position value %s exceeds maximum %s",
            position_value,
            MAX_POSITION
        )
        return

    # Calculate loss thresholds
    daily_drawdown = max(
        Decimal("0"),
        previous_equity - equity
    )

    total_drawdown = max(
        Decimal("0"),
        START_CAPITAL - equity
    )

    logging.info(
        "RISK: daily_drawdown=%s/%s total_drawdown=%s/%s position_value=%s/%s",
        daily_drawdown,
        DAILY_LOSS,
        total_drawdown,
        TOTAL_LOSS,
        position_value,
        MAX_POSITION
    )

    if (
        daily_drawdown >= DAILY_LOSS
        or total_drawdown >= TOTAL_LOSS
    ):
        decision(
            "HALT: loss threshold reached; manual review required"
        )
        return

    # Check whether the market is open
    clock = trading.get_clock()

    if not clock.is_open:
        decision("WAIT: market closed")
        return

    # Retrieve historical SPY market data
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

    # Exclude today's unfinished daily candle
    completed = sorted(
        (
            bar for bar in bars
            if bar.timestamp.astimezone(EASTERN).date() < today_et
        ),
        key=lambda bar: bar.timestamp
    )

    closes = [
        money(bar.close)
        for bar in completed
    ]

    if len(closes) < SLOW:
        decision(
            "HALT: insufficient completed daily bars (%s)",
            len(closes)
        )
        return

    # Calculate moving averages
    fast_ma = (
        sum(closes[-FAST:]) / Decimal(FAST)
    )

    slow_ma = (
        sum(closes[-SLOW:]) / Decimal(SLOW)
    )

    logging.info(
        "SIGNAL: SPY MA(%s)=%s MA(%s)=%s",
        FAST,
        fast_ma,
        SLOW,
        slow_ma
    )

    # Evaluate hypothetical sell signal
    if fast_ma <= slow_ma:
        if position:
            decision(
                "WOULD_SELL: trend below or equal to slow average; manual review"
            )
        else:
            decision(
                "STAY_CASH: trend below or equal to slow average"
            )
        return

    # Evaluate existing position
    if position:
        decision("HOLD: existing SPY position")
        return

    # Calculate hypothetical purchase amount
    budget = min(
        MAX_POSITION,
        cash - MIN_CASH_BUFFER
    )

    if budget < Decimal("1"):
        decision(
            "STAY_CASH: insufficient cash buffer"
        )
    else:
        decision(
            "WOULD_BUY: %s notional=%s (no order submitted)",
            SYMBOL,
            budget
        )


if __name__ == "__main__":
    run()
