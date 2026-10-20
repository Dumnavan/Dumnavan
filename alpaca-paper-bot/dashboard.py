
"""Alpaca paper account dashboard V3 - read only."""

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

START_CAPITAL = Decimal("50")
SYMBOL = "SPY"


def dec(value):
    return Decimal(str(value if value is not None else "0"))


def dollars(value):
    return f"${dec(value):,.2f}"


def esc(value):
    return html.escape(str(value), quote=True)


def log_value(pattern, log, default="N/A"):
    matches = re.findall(pattern, log)
    return matches[-1] if matches else default


def card(title, value, subtitle=""):
    return (
        '<div class="card">'
        f'<div class="label">{esc(title)}</div>'
        f'<div class="value">{esc(value)}</div>'
        f'<div class="detail">{esc(subtitle)}</div>'
        '</div>'
    )


def equity_chart(points):
    if not points:
        return '<p class="muted">No historical equity data available yet.</p>'

    values = [float(value) for _, value in points]
    low = min(values)
    high = max(values)
    padding = max((high - low) * 0.15, 0.02)
    low -= padding
    high += padding

    width, height = 900, 280
    left, right, top, bottom = 65, 20, 20, 45
    plot_w = width - left - right
    plot_h = height - top - bottom

    coords = []
    for i, (_, value) in enumerate(points):
        x = left + (
            plot_w * i / max(len(points) - 1, 1)
        )
        y = top + (
            plot_h * (high - float(value)) / (high - low)
        )
        coords.append((x, y))

    polyline = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in coords
    )

    grid = ""
    for i in range(5):
        value = high - (high - low) * i / 4
        y = top + plot_h * i / 4
        grid += (
            f'<line x1="{left}" y1="{y:.1f}" '
            f'x2="{width-right}" y2="{y:.1f}" '
            'stroke="#334155" stroke-dasharray="4 5"/>'
            f'<text x="{left-10}" y="{y+4:.1f}" '
            'text-anchor="end" fill="#94a3b8" font-size="12">'
            f'${value:.2f}</text>'
        )

    first_date = esc(points[0][0])
    last_date = esc(points[-1][0])

    return f"""
    <svg viewBox="0 0 {width} {height}"
         role="img" aria-label="Historical account equity chart">
        {grid}
        <polyline points="{polyline}"
                  fill="none"
                  stroke="#38bdf8"
                  stroke-width="3"
                  stroke-linejoin="round"
                  stroke-linecap="round"/>
        <circle cx="{coords[-1][0]:.1f}"
                cy="{coords[-1][1]:.1f}"
                r="5" fill="#86efac"/>
        <text x="{left}" y="{height-10}"
              fill="#94a3b8" font-size="12">{first_date}</text>
        <text x="{width-right}" y="{height-10}"
              text-anchor="end"
              fill="#94a3b8" font-size="12">{last_date}</text>
    </svg>
    <p class="muted">{len(points)} historical data point(s).</p>
    """


def main():
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    expected_id = os.environ["EXPECTED_PAPER_ACCOUNT_ID"].strip()

    if not expected_id:
        raise RuntimeError("EXPECTED_PAPER_ACCOUNT_ID is missing")

    trading = TradingClient(key, secret, paper=True)
    account = trading.get_account()

    if str(account.id) != expected_id:
        raise RuntimeError("Unexpected paper account ID")

    equity = dec(account.equity)
    cash = dec(account.cash)
    previous = dec(account.last_equity)
    total_return = equity - START_CAPITAL
    return_pct = total_return / START_CAPITAL * 100

    positions = trading.get_all_positions()
    if any(p.symbol != SYMBOL for p in positions):
        raise RuntimeError("Unexpected holdings detected")

    position = next(
        (p for p in positions if p.symbol == SYMBOL),
        None
    )

    qty = str(position.qty) if position else "0"
    market_value = dec(position.market_value) if position else dec(0)
    entry = dec(position.avg_entry_price) if position else dec(0)
    unrealized = dec(position.unrealized_pl) if position else dec(0)

    orders = trading.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=20
        )
    )

    # Fetch historical account equity from Alpaca.
    # Failure to fetch history will not hide current account data.
    points = []
    history_message = ""

    try:
        history = trading.get_portfolio_history(
            GetPortfolioHistoryRequest(
                period="1M",
                timeframe="1D"
            )
        )

        for timestamp, value in zip(
            history.timestamp or [],
            history.equity or []
        ):
            if value is None:
                continue

            date = datetime.fromtimestamp(
                int(timestamp),
                tz=timezone.utc
            ).strftime("%b %d")

            points.append((date, dec(value)))

        if not points:
            history_message = (
                "Alpaca has not returned historical equity points yet."
            )

    except Exception as exc:
        logging.warning(
            "Portfolio history unavailable: %s",
            type(exc).__name__
        )
        history_message = (
            "Historical data is temporarily unavailable."
        )

    log = (
        Path("bot.log").read_text(encoding="utf-8")
        if Path("bot.log").exists()
        else ""
    )

    fast = log_value(r"MA\(5\)=([\d.]+)", log)
    slow = log_value(r"MA\(20\)=([\d.]+)", log)
    decision = log_value(
        r"DECISION: ([^\n]+)",
        log,
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
            <td>{dollars(filled_price) if filled_price else "—"}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="6">No orders found.</td></tr>'

    cards = "".join([
        card("Account Equity", dollars(equity)),
        card("Available Cash", dollars(cash)),
        card(
            "Return Since $50 Start",
            f"{total_return:+.2f} USD",
            f"{return_pct:+.3f}%"
        ),
        card("SPY Market Value", dollars(market_value)),
        card("SPY Shares", qty),
        card("Average Entry Price", f"${entry:.3f}"),
        card("Unrealized SPY P/L", dollars(unrealized)),
        card(
            "Daily Drawdown",
            dollars(max(dec(0), previous - equity)),
            "$2.00 monitoring threshold"
        ),
        card(
            "Total Drawdown",
            dollars(max(dec(0), START_CAPITAL - equity)),
            "$10.00 monitoring threshold"
        ),
    ])

    updated = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alpaca Paper Bot V3</title>
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
<h1>Alpaca Paper Bot — V3</h1>
<p class="muted">Updated {esc(updated)}</p>
<p class="muted">
READ ONLY — No orders are submitted by this dashboard.
</p>

<div class="grid">{cards}</div>

<section class="panel">
<h2>Account Equity — Last Month</h2>
{equity_chart(points)}
<p class="muted">{esc(history_message)}</p>
<p class="muted">
Historical points come from Alpaca and may exclude
the latest intraday changes.
</p>
</section>

<section class="panel">
<h2>SPY Strategy</h2>
<p>5-day moving average: {esc(fast)}</p>
<p>20-day moving average: {esc(slow)}</p>
<p class="signal">{esc(decision)}</p>
<p class="muted">
Decision taken from the latest read-only bot log.
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
<tbody>{rows}</tbody>
</table>
</div>
</section>

<p class="muted">
Paper trading uses simulated money. Returns shown relative
to $50 assume no deposits or withdrawals since the start.
</p>
</main>
</body>
</html>"""

    Path("dashboard.html").write_text(
        page,
        encoding="utf-8"
    )
    logging.info("Dashboard V3 generated: dashboard.html")


if __name__ == "__main__":
    main()
