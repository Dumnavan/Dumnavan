
"""Generate a read-only HTML dashboard from Alpaca bot logs."""

import html
import re
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path("bot.log")
OUTPUT_FILE = Path("dashboard.html")

logs = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else ""


def extract(pattern, default="N/A"):
    matches = re.findall(pattern, logs)
    return matches[-1] if matches else default


def safe(value):
    return html.escape(str(value))


equity = extract(r"equity=([\d.]+)")
cash = extract(r"cash=([\d.]+)")
position = extract(r"position_value=([\d.]+)/")
daily = extract(r"daily_drawdown=([\d.]+)/")
total = extract(r"total_drawdown=([\d.]+)/")
fast = extract(r"MA\(5\)=([\d.]+)")
slow = extract(r"MA\(20\)=([\d.]+)")
decision = extract(r"DECISION: ([^\n]+)", "No decision recorded")

timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alpaca Paper Bot Dashboard</title>
<style>
body {{
    background: #0b1220;
    color: #e5e7eb;
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 30px;
}}
main {{ max-width: 950px; margin: auto; }}
h1 {{ margin-bottom: 5px; }}
.muted {{ color: #94a3b8; }}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin: 24px 0;
}}
.card {{
    background: #172235;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 20px;
}}
.label {{ color: #94a3b8; font-size: 14px; }}
.value {{ font-size: 30px; font-weight: bold; margin-top: 10px; }}
.track {{
    background: #334155;
    border-radius: 8px;
    height: 12px;
    overflow: hidden;
    margin: 12px 0;
}}
.fill {{
    background: #38bdf8;
    height: 100%;
}}
.decision {{
    color: #86efac;
    font-size: 20px;
    overflow-wrap: anywhere;
}}
</style>
</head>
<body>
<main>
<h1>Alpaca Paper Bot</h1>
<p class="muted">Read-only strategy dashboard | {safe(timestamp)}</p>

<div class="grid">
  <div class="card">
    <div class="label">Account Equity</div>
    <div class="value">${safe(equity)}</div>
  </div>
  <div class="card">
    <div class="label">Available Cash</div>
    <div class="value">${safe(cash)}</div>
  </div>
  <div class="card">
    <div class="label">SPY Position Value</div>
    <div class="value">${safe(position)}</div>
  </div>
</div>

<div class="card">
  <h2>Risk Management</h2>
  <p>Daily drawdown: ${safe(daily)} / $2</p>
  <div class="track"><div class="fill" style="width:{min(100, float(daily) / 2 * 100) if daily != 'N/A' else 0}%"></div></div>
  <p>Total drawdown: ${safe(total)} / $10</p>
  <div class="track"><div class="fill" style="width:{min(100, float(total) / 10 * 100) if total != 'N/A' else 0}%"></div></div>
</div>

<div class="grid">
  <div class="card">
    <div class="label">SPY 5-Day Moving Average</div>
    <div class="value">${safe(fast)}</div>
  </div>
  <div class="card">
    <div class="label">SPY 20-Day Moving Average</div>
    <div class="value">${safe(slow)}</div>
  </div>
</div>

<div class="card">
  <h2>Latest Strategy Decision</h2>
  <p class="decision">{safe(decision)}</p>
  <p class="muted">Analysis only. No orders submitted.</p>
</div>
</main>
</body>
</html>"""

OUTPUT_FILE.write_text(page, encoding="utf-8")
print("Dashboard generated:", OUTPUT_FILE)
