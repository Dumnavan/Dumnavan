
"""Read-only Alpaca paper-account trend experiment. Never submits orders."""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

SYMBOL = "SPY"
START_CAPITAL = Decimal("50")
MAX_POSITION = Decimal("10")
DAILY_LOSS = Decimal("2")
TOTAL_LOSS = Decimal("10")

FAST = 5
SLOW = 20

EASTERN = ZoneInfo("America/New_York")


def run():
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]

    # Connect exclusively to paper trading
    trading = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)

    account = trading.get_account()
    clock = trading.get_clock()

    equity = Decimal(str(account.equity))
    previous = Decimal(str(account.last_equity))
    cash = Decimal(str(account.cash))

    logging.info(
        "READ-ONLY TEST: paper equity=%s cash=%s previous=%s",
        equity,
        cash,
        previous
    )

    # Verify the account starts with $50
    if not (Decimal("49.99") <= equity <= Decimal("50.01")):
        raise RuntimeError(
            "Expected a fresh $50 paper account; no action taken"
        )

    # Check account restrictions
    if account.trading_blocked or account.account_blocked:
        raise RuntimeError(
            "Account is blocked; no action taken"
        )

    # Check positions and open orders
    positions = trading.get_all_positions()

    orders = trading.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.OPEN
        )
    )

    if any(p.symbol != SYMBOL for p in positions):
        raise RuntimeError(
            "Unexpected holding detected; no action taken"
        )

    if orders:
        logging.info(
            "Open orders found: would wait for resolution"
        )
        return

    position = next(
        (p for p in positions if p.symbol == SYMBOL),
        None
    )

    # Check loss thresholds
    if (
        previous - equity >= DAILY_LOSS
        or START_CAPITAL - equity >= TOTAL_LOSS
    ):
        logging.warning(
            "Loss threshold breached: would halt and review account"
        )
        return

    # Only analyze during regular market hours
    if not clock.is_open:
        logging.info(
            "Market closed: read-only test finished"
        )
        return

    # Retrieve historical SPY prices
    now = datetime.now(timezone.utc)

    bars = data.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=SYMBOL,
            timeframe=TimeFrame.Day,
            start=now - timedelta(days=90),
            end=now,
            feed="iex",
        )
    ).data.get(SYMBOL, [])

    # Exclude today's unfinished trading candle
    today_et = now.astimezone(EASTERN).date()

    completed = sorted(
        (
            bar for bar in bars
            if bar.timestamp.astimezone(EASTERN).date() < today_et
        ),
        key=lambda bar: bar.timestamp
    )

    closes = [
        Decimal(str(bar.close))
        for bar in completed
    ]

    if len(closes) < SLOW:
        raise RuntimeError(
            "Insufficient completed daily bars"
        )

    # Calculate moving averages
    fast_ma = sum(closes[-FAST:]) / Decimal(FAST)
    slow_ma = sum(closes[-SLOW:]) / Decimal(SLOW)

    logging.info(
        "SPY completed-bar MA(%s)=%s MA(%s)=%s",
        FAST,
        fast_ma,
        SLOW,
        slow_ma
    )

    # Evaluate hypothetical trading decisions
    if fast_ma <= slow_ma:
        if position:
            logging.info(
                "DRY RUN: would close SPY"
            )
        else:
            logging.info(
                "DRY RUN: would stay in cash"
            )

    elif position:
        logging.info(
            "DRY RUN: would hold existing SPY position"
        )

    else:
        budget = min(
            MAX_POSITION,
            cash - Decimal("1")
        )

        if budget >= Decimal("1"):
            logging.info(
                "DRY RUN: would consider buying SPY for $%s",
                budget
            )
        else:
            logging.info(
                "DRY RUN: insufficient available cash"
            )


if __name__ == "__main__":
    run()
