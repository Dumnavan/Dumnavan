# Alpaca Paper Bot v1

**Simulation only.** Uses Alpaca paper trading, hardcoded in `bot.py`. Never put credentials in source files, chat messages, or public logs.

## Setup
1. Create an Alpaca account and select **Paper Trading**. Reset its paper equity to **$50** and keep this account dedicated to the experiment.
2. Create a **private GitHub repository**, then upload `bot.py`, `requirements.txt`, and `.github/workflows/paper-bot.yml` preserving the folder paths.
3. In GitHub, open **Settings → Secrets and variables → Actions → New repository secret**. Add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` using your **paper** API credentials (never live keys).
4. Open **Actions → Alpaca Paper Bot → Run workflow** to test manually. Review logs for errors and confirm in Alpaca that any order is labeled **paper**.
5. The workflow is also scheduled every 15 minutes on weekdays; Alpaca's market clock prevents orders outside regular sessions. Scheduled GitHub jobs may be delayed, skipped, or disabled due to inactivity.
6. To stop the bot, disable the workflow under **Actions**. To stop orders already placed, cancel them in Alpaca paper dashboard. Disabling the workflow does **not** close positions or cancel existing orders.

## Strategy
- Symbol: SPY only, long-only.
- Uses prior completed daily bars from IEX, not live intraday pricing.
- If 5-day SMA > 20-day SMA and no position exists, submits a fractional-share **$10 or less** market buy.
- If 5-day SMA <= 20-day SMA, closes any SPY position.
- Only one position; refuses to trade when other positions or open orders exist.
- Daily cutoff: previous close equity minus current equity >= $2. Total cutoff: $50 minus current equity >= $10. When breached, tries to close the position and prevents new buys.

## Important limitations
- This is **not AI-driven** yet; it is a transparent baseline to evaluate before AI signals.
- No guaranteed stop-loss: checks run periodically, and orders can execute at unfavorable prices. Losses may exceed thresholds.
- The $50 baseline assumes no cash transfers and a dedicated $50 account. If the account balance rises above $55, the bot stops as a protective sanity check (which also stops it after substantial gains).
- A paper account can fill orders unrealistically; results do not establish real-money profitability.
- The strategy uses daily trend data and can remain idle for extended periods.
- `get_orders()` is deliberately conservative; any order returned blocks new trades. Inspect the Alpaca dashboard if it seems stuck.
- GitHub Actions is best-effort, not an always-on execution service.
- This bot does not perform historical backtesting, record trades in a database, or calculate commissions/taxes. Use Alpaca order history to inspect simulated fills.
