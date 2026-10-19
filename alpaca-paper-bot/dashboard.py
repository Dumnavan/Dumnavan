
"""Read-only dashboard for an Alpaca paper-trading account."""

import html
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

logging.basicConfig(level=logging.INFO)

SYMBOL = "SPY"
START_CAPITAL = Decimal("50")
DAILY_LIMIT = Decimal("2")
TOTAL_LIMIT = Decimal("10")
POSITION_LIMIT = Decimal("10")


def money(value):
    return Decimal(str(value or "0"))


def fmt(value, places=2):
    return f"${money(value):,.{places}f}"


def safe(value):
    return html.escape(str(value), quote=True)


def get_log_value(pattern, logs, default="N/A"):
    matches = re.findall(pattern, logs)
    return matches[-1] if matches else default


def progress(value, limit):
    percentage = max(
        Decimal("0"),
        min(Decimal("100"), money(value) / limit * 100)
    )
    return float(percentage)


def main():
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    expected_id = os.environ["EXPECTED_PAPER_ACCOUNT_ID"].strip()

    if not expected_id:
        raise RuntimeError("Paper account ID is missing")

    # Read-only Alpaca API calls, paper account only.
    client = TradingClient(key, secret, paper=True)
    account = client.get_account()

    if str(account.id) != expected_id:
        raise RuntimeError("Paper account ID mismatch")

    positions = client.get_all_positions()

    if any(p.symbol != SYMBOL for p in positions):
        raise RuntimeError(
            "Unexpected holdings detected; dashboard not generated"
        )

    position = next(
        (p for p in positions if p.symbol == SYMBOL),
        None
    )

    orders = client.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=20
        )
    )

    equity = money(account.equity)
    cash = money(account.cash)
    previous = money(account.last_equity)

    daily_drawdown = max(Decimal("0"), previous - equity)
    total_drawdown = max(Decimal("0"), START_CAPITAL - equity)

    if position:
        quantity = str(position.qty)
        market_value = money(position.market_value)
        entry_price = money(position.avg_entry_price)
        unrealized_pl = money(position.unrealized_pl)
        unrealized_pct = money(position.unrealized_plpc) * 100
    else:
        quantity = "0"
        market_value = Decimal("0")
        entry_price = Decimal("0")
        unrealized_pl = Decimal("0")
        unrealized_pct = Decimal("0")

    logs = (
        Path("bot.log").read_text(encoding="utf-8")
        if Path("bot.log").exists()
        else ""
    )

    fast = get_log_value(r"MA\(5\)=([\d.]+)", logs)
    slow = get_log_value(r"MA\(20\)=([\d.]+)", logs)
    decision = get_log_value(
        r"DECISION: ([^\n]+)",
        logs,
        "No strategy decision recorded"
    )

    # Build recent order history.
    order_rows = ""

    for order in orders[:5]:
        submitted = getattr(order, "submitted_at", None)
        date_text = (
            submitted.strftime("%Y-%m-%d %H:%M UTC")
            if submitted
            else "N/A"
        )

        side = getattr(order.side, "value", str(order.side))
        status = getattr(order.status, "value", str(order.status))

        filled_qty = getattr(order, "filled_qty", None)
        filled_price = getattr(order, "filled_avg_price", None)

        order_rows += f"""
        <tr>
            <td>{safe(date_text)}</td>
            <td>{safe(order.symbol)}</td>
            <td>{safe(side)}</td>
            <td>{safe(status)}</td>
            <td>{safe(filled_qty or "0")}</td>
            <td>{fmt(filled_price) if filled_price else "—"}</td>
        </tr>
        """

    if not order_rows:
        order_rows = """
        <tr><td colspan="6">No recent orders found</td></tr>
        """

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    def card(label, value, detail=""):
        return f"""
        <div class="card">
            <div class="label">{safe(label)}</div>
            <div class="value">{safe(value)}</div>
            <div class="detail">{safe(detail)}</div>
        </div>
        """

    account_cards = "".join([
        card("Account Equity", fmt(equity)),
        card("Available Cash", fmt(cash)),
        card("SPY Market Value", fmt(market_value)),
        card("SPY Shares", quantity),
        card("Average Entry Price", fmt(entry_price, 3)),
        card(
            "Unrealized P/L",
            fmt(unrealized_pl),
            f"{unrealized_pct:+.3f}%"
        ),
    ])

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alpaca Paper Bot Dashboard</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    padding: 28px;
    background: #0b1220;
    color: #f1f5f9;
    font-family: Arial, sans-serif;
}}
main {{ max-width: 1100px; margin: auto; }}
h1 {{ margin-bottom: 8px; }}
h2 {{ margin-top: 0; }}
.muted, .label, .detail {{ color: #94a3b8; }}
.label {{ font-size: 14px; }}
.detail {{ margin-top: 8px; font-size: 13px; }}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin: 24px 0;
}}
.card, .panel {{
    background: #172235;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 20px;
}}
.panel {{ margin: 20px 0; }}
.value {{
    font-size: 28px;
    font-weight: bold;
    margin-top: 10px;
}}
.track {{
    height: 12px;
    background: #334155;
    border-radius: 8px;
    overflow: hidden;
}}
.fill {{
    height: 100%;
    background: #38bdf8;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    min-width: 650px;
}}
th, td {{
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid #334155;
    font-size: 14px;
}}
th {{ color: #94a3b8; }}
.table-wrap {{ overflow-x: auto; }}
.signal {{
    font-size: 19px;
    color: #86efac;
    overflow-wrap: anywhere;
}}
</style>
</head>
<body>
<main>
<h1>Alpaca Paper Bot</h1>
<p class="muted">
Paper account dashboard | Updated {safe(timestamp)}
</p>
<p class="muted">
READ ONLY — This dashboard never submits orders.
</p>

<div class="grid">
{account_cards}
</div>

<section class="panel">
<h2>Risk Management</h2>

<p>Daily drawdown: {fmt(daily_drawdown)} / $2.00</p>
<div class="track">
<div class="fill" style="width:{progress(daily_drawdown, DAILY_LIMIT)}%"></div>
</div>

<p>Total drawdown: {fmt(total_drawdown)} / $10.00</p>
<div class="track">
<div class="fill" style="width:{progress(total_drawdown, TOTAL_LIMIT)}%"></div>
</div>

<p>SPY exposure: {fmt(abs(market_value))} / $10.00</p>
<div class="track">
<div class="fill" style="width:{progress(abs(market_value), POSITION_LIMIT)}%"></div>
</div>

<p class="muted">
Risk thresholds are monitoring checks, not guaranteed stop-losses.
</p>
</section>

<section class="panel">
<h2>SPY Strategy</h2>
<p>5-day moving average: {safe(fast)}</p>
<p>20-day moving average: {safe(slow)}</p>
<p class="signal">{safe(decision)}</p>
<p class="muted">
The decision comes from the latest dry-run analysis.
</p>
</section>

<section class="panel">
<h2>Recent Paper Orders</h2>
<div class="table-wrap">
<table>
<thead>
<tr>
<th>Submitted</th>
<th>Symbol</th>
<th>Side</th>
<th>Status</th>
<th>Filled Shares</th>
<th>Average Fill</th>
</tr>
</thead>
<tbody>
{order_rows}
</tbody>
</table>
</div>
</section>

<p class="muted">
Paper trading is simulated. Performance is not a prediction
of live trading results.
</p>
</main>
</body>
</html>"""

    Path("dashboard.html").write_text(
        page,
        encoding="utf-8"
    )

    logging.info(
        "Dashboard generated successfully: dashboard.html"
    )


if __name__ == "__main__":
    main()
