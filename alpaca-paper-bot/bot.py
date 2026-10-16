"""Paper-only, scheduled Alpaca trading experiment. Not investment advice."""
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
SYMBOL = 'SPY'
START_CAPITAL = Decimal('50')
MAX_POSITION = Decimal('10')
DAILY_LOSS = Decimal('2')
TOTAL_LOSS = Decimal('10')
FAST = 5
SLOW = 20


def run():
    key = os.environ['ALPACA_API_KEY']
    secret = os.environ['ALPACA_SECRET_KEY']
    # Intentionally hardcoded paper=True: no live-trading toggle.
    trading = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)
    account = trading.get_account()
    clock = trading.get_clock()
    equity = Decimal(str(account.equity))
    previous = Decimal(str(account.last_equity))
    logging.info('Paper account equity: %s; previous close equity: %s', equity, previous)

    # Refuse to run if this account was not initialized near $50.
    # Reset a new paper account to $50 before using this bot.
    if equity > Decimal('55'):
        raise RuntimeError('Equity exceeds $55; verify this is a dedicated $50 paper account')

    if not clock.is_open:
        logging.info('Market closed: no action')
        return

    positions = trading.get_all_positions()
   orders = trading.get_orders(
    filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)
)
    if any(p.symbol != SYMBOL for p in positions):
        raise RuntimeError('Unexpected holding detected; refusing to trade')
    if orders:
        logging.info('Existing order(s) detected; no new orders')
        return

    position = next((p for p in positions if p.symbol == SYMBOL), None)
    daily_breach = previous - equity >= DAILY_LOSS
    total_breach = START_CAPITAL - equity >= TOTAL_LOSS
    if daily_breach or total_breach:
        logging.warning('Loss limit breached (daily=%s, total=%s)', daily_breach, total_breach)
        if position:
            trading.close_position(SYMBOL)
            logging.warning('Submitted paper liquidation order')
        return

    now = datetime.now(timezone.utc)
    bars = data.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Day,
        start=now - timedelta(days=65),
        end=now - timedelta(days=1),
        feed='iex',
    )).data.get(SYMBOL, [])
    closes = [Decimal(str(b.close)) for b in sorted(bars, key=lambda b: b.timestamp)]
    if len(closes) < SLOW:
        raise RuntimeError('Insufficient daily history for moving averages')
    fast_ma = sum(closes[-FAST:]) / FAST
    slow_ma = sum(closes[-SLOW:]) / SLOW
    logging.info('SPY 5-day MA=%s, 20-day MA=%s', fast_ma, slow_ma)

    if fast_ma <= slow_ma:
        if position:
            trading.close_position(SYMBOL)
            logging.info('Trend down: submitted paper close order')
        else:
            logging.info('Trend down: stay in cash')
        return

    if position:
        logging.info('Position already held: no action')
        return

    cash = Decimal(str(account.cash))
    budget = min(MAX_POSITION, cash - Decimal('1'))
    if budget < Decimal('1'):
        logging.info('Insufficient cash buffer: no action')
        return
    # Fractional market buys via notional, during regular market hours only.
    order = MarketOrderRequest(
        symbol=SYMBOL,
        notional=round(float(budget), 2),
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    submitted = trading.submit_order(order)
    logging.info('Submitted paper BUY %s notional=$%.2f order=%s', SYMBOL, float(budget), submitted.id)


if __name__ == '__main__':
    run()
