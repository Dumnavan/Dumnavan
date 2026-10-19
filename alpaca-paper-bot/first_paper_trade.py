
"""One-time, manually confirmed $10 SPY paper purchase."""

import os
import logging
from decimal import Decimal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s"
)

SYMBOL = "SPY"
ORDER_AMOUNT = Decimal("10")
START_CAPITAL = Decimal("50")


def money(value):
    return Decimal(str(value))


def main():
    if os.getenv("CONFIRM_PAPER_ORDER") != "CONFIRM_PAPER_BUY_10":
        raise RuntimeError("Manual confirmation missing")

    expected_id = os.environ["EXPECTED_PAPER_ACCOUNT_ID"].strip()

    if not expected_id:
        raise RuntimeError("Expected account ID missing")

    client = TradingClient(
        os.environ["ALPACA_API_KEY"],
        os.environ["ALPACA_SECRET_KEY"],
        paper=True,
    )

    account = client.get_account()

    if str(account.id) != expected_id:
        raise RuntimeError("Wrong paper account")

    if account.account_blocked or account.trading_blocked:
        raise RuntimeError("Account is blocked")

    equity = money(account.equity)
    previous = money(account.last_equity)
    cash = money(account.cash)

    if previous - equity >= Decimal("2"):
        raise RuntimeError("Daily loss threshold reached")

    if START_CAPITAL - equity >= Decimal("10"):
        raise RuntimeError("Total loss threshold reached")

    if cash < ORDER_AMOUNT + Decimal("1"):
        raise RuntimeError("Insufficient cash buffer")

    if not client.get_clock().is_open:
        raise RuntimeError("Market is closed")

    positions = client.get_all_positions()

    if positions:
        raise RuntimeError(
            "Existing holdings detected; no purchase"
        )

    open_orders = client.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.OPEN
        )
    )

    if open_orders:
        raise RuntimeError(
            "Existing open orders detected"
        )

    asset = client.get_asset(SYMBOL)

    if not asset.tradable or not asset.fractionable:
        raise RuntimeError(
            "SPY is not available for fractional trading"
        )

    # Reuse the same ID if this workflow run is retried.
    run_id = os.environ["GITHUB_RUN_ID"]
    client_order_id = f"first-spy-{run_id}"

    order = MarketOrderRequest(
        symbol=SYMBOL,
        notional=float(ORDER_AMOUNT),
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )

    logging.info(
        "Submitting PAPER BUY: %s notional=$%s",
        SYMBOL,
        ORDER_AMOUNT,
    )

    result = client.submit_order(order)

    logging.info(
        "PAPER ORDER SUBMITTED: status=%s",
        result.status,
    )
    logging.info(
        "Check Alpaca paper dashboard for fill status"
    )


if __name__ == "__main__":
    main()
