
import os
from decimal import Decimal
from alpaca.trading.client import TradingClient

# Connect exclusively to paper trading
client = TradingClient(
    os.environ["ALPACA_API_KEY"],
    os.environ["ALPACA_SECRET_KEY"],
    paper=True
)

account = client.get_account()

equity = Decimal(str(account.equity))
cash = Decimal(str(account.cash))

print("Paper API connection successful")
print("Account status:", account.status)
print("Account equity:", equity)
print("Available cash:", cash)

# Verify the correct $50 account
if not Decimal("49.99") <= equity <= Decimal("50.01"):
    raise RuntimeError(
        "Incorrect paper account balance. "
        "Expected $50."
    )

print("Account balance verified!")
