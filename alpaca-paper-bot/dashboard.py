
"""Alpaca Paper Bot Dashboard V3.1 - read-only performance tracking."""

import html
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import (
    GetOrdersRequest,
    GetPortfolioHistoryRequest,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SYMBOL = "SPY"
START_CAPITAL = Decimal("50")
DAILY_LOSS_LIMIT = Decimal("2")
TOTAL_LOSS_LIMIT = Decimal("10")


def dec(value):
    return Decimal(str(value if value is not None else "0"))


def usd(value):
    value = dec(value)
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def signed_usd(value):
    value = dec(value)
    sign = "+" if value > 0 else ""
    return sign + usd(value)


def esc(value):
    return html.escape(str(value), quote=True)


def log_value(pattern, content, default="N/A"):
    matches = re.findall(pattern, content)
    return matches[-1] if matches else default


def card(label, value, detail=""):
    return f"""
    <div class="card">
      <div class="label">{esc(label)}</div>
      <div class="value">{esc(value)}</div>
      <div class="detail">{esc(detail)}</div>
    </div>
    """


def make_chart(points):
    if not points:
        return '<p class="muted">No funded-account history available yet.</p>'

    values = [float(equity) for _, equity in points]

    minimum = min(values)
    maximum = max(values)

    # Keep a small visible range even if equity barely changes.
    padding = max((maximum - minimum) * 0.2, 0.05)
    minimum -= padding
    maximum += padding

    width = 900
    height = 300
    left = 75
    right = 25
    top = 20
    bottom = 50

    plot_width = width - left - right
    plot_height = height - top - bottom

    coordinates = []

    for index, (_, value) in enumerate(points):
        x = left + (
            plot_width * index / max(len(points) - 1, 1)
        )
        y = top + (
            plot_height * (maximum - float(value))
            / (maximum - minimum)
        )
        coordinates.append((x, y))

    grid = ""

    for i in range(5):
        amount = maximum - (maximum - minimum) * i / 4
        y = top + plot_height * i / 4

        grid += f"""
        <line x1="{left}" y1="{y:.2f}"
              x2="{width-right}" y2="{y:.2f}"
              stroke="#334155" stroke-dasharray="4 5"/>
        <text x="{left-12}" y="{y+4:.2f}"
              text-anchor="end" fill="#94a3b8"
              font-size="12">${amount:.2f}</text>
        """

    line = " ".join(
        f"{x:.2f},{y:.2f}" for x, y in coordinates
    )

    circles = ""

    for x, y in coordinates:
        circles += (
            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
            'r="3" fill="#38bdf8"/>'
        )

    return f"""
    <svg viewBox="0 0 {width} {height}"
         role="img"
         aria-label="Paper account equity since funding">
      {grid}
      <polyline points="{line}"
                fill="none"
                stroke="#38bdf8"
                stroke-width="3"
                stroke-linejoin="round"/>
      {circles}
      <text x="{left}" y="{height-12}"
            fill="#94a3b8" font-size="12">
        {esc(points[0][0])}
      </text>
      <text x="{width-right}" y="{height-12}"
            text-anchor="end"
            fill="#94a3b8" font-size="12">
        {esc(points[-1][0])}
      </text>
    </svg>
    <p class="muted">
      {len(points)} funded-account data point(s).
    </p>
    """


def main():
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    expected_id = os.environ["EXPECTED_PAPER_ACCOUNT_ID"].strip()

    if not expected_id:
        raise RuntimeError("Expected paper account ID is missing")

    client = TradingClient(key, secret, paper=True)
    account = client.get_account()

    if str(account.id) != expected_id:
        raise RuntimeError("Unexpected paper account ID")

    equity = dec(account.equity)
    cash = dec(account.cash)
    previous_equity = dec(account.last_equity)

    positions = client.get_all_positions()

    if any(p.symbol != SYMBOL for p in positions):
        raise RuntimeError("Unexpected holdings detected")

    position = next(
        (p for p in positions if p.symbol == SYMBOL),
        None
    )

    quantity = str(position.qty) if position else "0"
    market_value = dec(position.market_value) if position else dec(0)
    entry_price = dec(position.avg_entry_price) if position else dec(0)
    unrealized_pl = dec(position.unrealized_pl) if position else dec(0)

    orders = client.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=20
        )
    )

    # Retrieve historical equity and funding-adjusted P/L.
    points = []
    history_note = ""
    performance_pl = None
    performance_pct = None

    try:
        history = client.get_portfolio_history(
            GetPortfolioHistoryRequest(
                period="1M",
                timeframe="1D"
            )
        )

        timestamps = history.timestamp or []
        equities = history.equity or []

        # A nonzero balance alone does not prove an account was
        # funded. Here we use the first balance near our known
        # starting amount as the beginning of the chart.
        funding_threshold = START_CAPITAL * Decimal("0.90")
        funded = False

        for timestamp, value in zip(timestamps, equities):
            if value is None:
                continue

            amount = dec(value)

            if not funded:
                if amount < funding_threshold:
                    continue
                funded = True

            date = datetime.fromtimestamp(
                int(timestamp), timezone.utc
            ).strftime("%b %d")

            points.append((date, amount))

        # Alpaca's profit_loss history is adjusted for cashflows.
        # It is more meaningful than equity minus $50 when
        # deposits or withdrawals may have occurred.
        pl_values = [
            dec(value)
            for value in (history.profit_loss or [])
            if value is not None
        ]

        pct_values = [
            dec(value)
            for value in (history.profit_loss_pct or [])
            if value is not None
        ]

        if pl_values:
            performance_pl = pl_values[-1]

        if pct_values:
            performance_pct = pct_values[-1] * 100

        if not points:
            history_note = (
                "No funded-account daily history found yet."
            )

    except Exception as exc:
        logging.warning(
            "Portfolio history unavailable: %s",
            type(exc).__name__
        )
        history_note = "Portfolio history temporarily unavailable."

    # Starting-capital return assumes no subsequent transfers.
    equity_change = equity - START_CAPITAL
    equity_change_pct = equity_change / START_CAPITAL * 100

    daily_drawdown = max(
        dec(0), previous_equity - equity
    )
    total_drawdown = max(
        dec(0), START_CAPITAL - equity
    )

    logs = (
        Path("bot.log").read_text(encoding="utf-8")
        if Path("bot.log").exists()
        else ""
    )

    fast = log_value(r"MA\(5\)=([\d.]+)", logs)
    slow = log_value(r"MA\(20\)=([\d.]+)", logs)
    decision = log_value(
        r"DECISION: ([^\n]+)",
        logs,
        "No decision recorded"
    )

    rows = ""

    for order in orders[:5]:
        submitted = getattr(order, "submitted_at", None)

        date = (
            submitted.strftime("%Y-%m-%d %H:%M UTC")
            if submitted else "N/A"
        )

        side = getattr(order.side, "value", str(order.side))
        status = getattr(order.status, "value", str(order.status))
        filled_qty = getattr(order, "filled_qty", None) or "0"
        filled_price = getattr(order, "filled_avg_price", None)

        rows += f"""
        <tr>
          <td>{esc(date)}</td>
          <td>{esc(order.symbol)}</td>
          <td>{esc(side)}</td>
          <td>{esc(status)}</td>
          <td>{esc(filled_qty)}</td>
          <td>{usd(filled_price) if filled_price else "—"}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="6">No orders found.</td></tr>'

    cards = "".join([
        card("Account Equity", usd(equity)),
        card("Available Cash", usd(cash)),
        card(
            "Equity Change Since $50",
            signed_usd(equity_change),
            f"{equity_change_pct:+.3f}% — assumes no transfers"
        ),
        card("SPY Market Value", usd(market_value)),
        card("SPY Shares", quantity),
        card("Average Entry Price", f"${entry_price:.3f}"),
        card("Unrealized SPY P/L", signed_usd(unrealized_pl)),
        card(
            "Daily Drawdown",
            usd(daily_drawdown),
            f"Monitoring threshold: {usd(DAILY_LOSS_LIMIT)}"
        ),
        card(
            "Total Drawdown",
            usd(total_drawdown),
            f"Monitoring threshold: {usd(TOTAL_LOSS_LIMIT)}"
        ),
    ])

    performance_section = ""

    if performance_pl is not None:
        pct_text = (
            f"{performance_pct:+.3f}%"
            if performance_pct is not None
            else "Percentage unavailable"
        )

        performance_section = f"""
        <div class="panel">
          <h2>Alpaca Portfolio Performance</h2>
          <div class="value">{esc(signed_usd(performance_pl))}</div>
          <p>{esc(pct_text)}</p>
          <p class="muted">
            Based on Alpaca's portfolio-history performance
            fields for the requested one-month period.
            This is not necessarily lifetime performance.
          </p>
        </div>
        """

    updated = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alpaca Paper Bot V3.1</title>
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
.label {{ font-size: 14px; }}
.value {{
    font-size: 26px;
    font-weight: bold;
    margin-top: 10px;
}}
.detail {{ font-size: 13px; margin-top: 8px; }}
svg {{ width: 100%; height: auto; }}
table {{
    width: 100%;
    min-width: 650px;
    border-collapse: collapse;
}}
th, td {{
    padding: 12px;
    border-bottom: 1px solid #334155;
    text-align: left;
    font-size: 14px;
}}
th {{ color: #94a3b8; }}
.table-wrap {{ overflow-x: auto; }}
.signal {{
    color: #86efac;
    font-size: 18px;
    overflow-wrap: anywhere;
}}
</style>
</head>
<body>
<main>
<h1>Alpaca Paper Bot — V3.1</h1>
<p class="muted">Updated {esc(updated)}</p>
<p class="muted">
READ ONLY — Dashboard does not submit orders.
</p>

<div class="grid">{cards}</div>

<section class="panel">
<h2>Account Equity — Since Initial Funding</h2>
{make_chart(points)}
<p class="muted">{esc(history_note)}</p>
<p class="muted">
Daily historical equity is filtered to begin near
the original $50 funding amount. Later deposits or
withdrawals are not removed from this equity chart.
</p>
</section>

{performance_section}

<section class="panel">
<h2>SPY Strategy</h2>
<p>5-day moving average: {esc(fast)}</p>
<p>20-day moving average: {esc(slow)}</p>
<p class="signal">{esc(decision)}</p>
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
<tbody>{rows}</tbody>
</table>
</div>
</section>

<p class="muted">
Paper trading uses simulated funds and does not
guarantee live-trading performance.
</p>
</main>
</body>
</html>"""

    Path("dashboard.html").write_text(
        page, encoding="utf-8"
    )

    logging.info("Dashboard V3.1 generated successfully")


if __name__ == "__main__":
    main()
