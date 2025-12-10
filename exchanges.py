"""
Exchange integration module using ccxt library.
Handles all communication with cryptocurrency exchanges.
"""

import os
from typing import Optional, Literal, Any
import ccxt

import config
from logger import get_logger

logger = get_logger(__name__)


class ExchangeManager:
    """Manages connections and operations for multiple cryptocurrency exchanges."""

    def __init__(self, exchange_ids: list[str]) -> None:
        """
        Initialize exchange instances for each supported exchange.
        API keys are loaded from environment variables.
        """
        self.exchanges: dict[str, ccxt.Exchange] = {}
        self.exchange_ids = exchange_ids

        for exchange_id in exchange_ids:
            try:
                self._init_exchange(exchange_id)
            except Exception as e:
                logger.error(f"Failed to initialize {exchange_id}: {e}")

    def _init_exchange(self, exchange_id: str) -> None:
        """Initialize a single exchange with API credentials from environment."""
        exchange_id_upper = exchange_id.upper()
        api_key = os.getenv(f"{exchange_id_upper}_API_KEY", "")
        api_secret = os.getenv(f"{exchange_id_upper}_API_SECRET", "")

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            logger.error(f"Exchange {exchange_id} not supported by ccxt")
            return

        exchange_config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }

        if exchange_id == "okx":
            passphrase = os.getenv("OKX_PASSPHRASE", "")
            exchange_config["password"] = passphrase
            exchange_config["hostname"] = "my.okx.com"

        self.exchanges[exchange_id] = exchange_class(exchange_config)
        logger.info(f"Initialized exchange: {exchange_id}")

    def load_markets(self) -> None:
        """Load markets for all initialized exchanges."""
        for exchange_id, exchange in self.exchanges.items():
            try:
                exchange.load_markets()
                markets = exchange.markets or {}
                logger.info(f"Loaded markets for {exchange_id}: {len(markets)} pairs")
            except Exception as e:
                logger.error(f"Failed to load markets for {exchange_id}: {e}")

    def get_exchange(self, exchange_id: str) -> Optional[ccxt.Exchange]:
        """Return the ccxt exchange instance for the given ID."""
        return self.exchanges.get(exchange_id)

    def get_ticker(self, exchange_id: str, symbol: str) -> Optional[dict]:
        """
        Fetch the current ticker (bid/ask) for a symbol on an exchange.
        Returns None if the fetch fails.
        """
        exchange = self.exchanges.get(exchange_id)
        if exchange is None:
            logger.error(f"Exchange {exchange_id} not initialized")
            return None

        try:
            ticker = exchange.fetch_ticker(symbol)
            return {
                "bid": ticker.get("bid"),
                "ask": ticker.get("ask"),
                "last": ticker.get("last"),
                "symbol": symbol,
                "exchange": exchange_id
            }
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol} on {exchange_id}: {e}")
            return None

    def get_balances(self, exchange_id: str) -> dict:
        """
        Fetch current balances for an exchange.
        Returns empty dict if fetch fails.
        """
        exchange = self.exchanges.get(exchange_id)
        if exchange is None:
            logger.error(f"Exchange {exchange_id} not initialized")
            return {}

        try:
            balance = exchange.fetch_balance()
            return balance.get("free", {})
        except Exception as e:
            logger.error(f"Failed to fetch balances for {exchange_id}: {e}")
            return {}

    def create_order(
        self,
        exchange_id: str,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None
    ) -> dict:
        """
        Create an order on the specified exchange.
        In DRY_RUN mode, simulates the order without sending to exchange.
        """
        exchange = self.exchanges.get(exchange_id)
        if exchange is None:
            logger.error(f"Exchange {exchange_id} not initialized")
            return {"error": "Exchange not initialized"}

        order_info = (
            f"Exchange: {exchange_id} | Symbol: {symbol} | Side: {side} | "
            f"Type: {order_type} | Amount: {amount:.8f} | Price: {price}"
        )

        if config.DRY_RUN:
            logger.info(f"[DRY_RUN] SIMULATED ORDER: {order_info}")
            return {
                "id": "SIMULATED",
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "amount": amount,
                "price": price,
                "status": "simulated",
                "exchange": exchange_id
            }

        try:
            if order_type == "market":
                order = exchange.create_order(symbol, order_type, side, amount)  # type: ignore
            else:
                order = exchange.create_order(symbol, order_type, side, amount, price)  # type: ignore

            logger.info(f"ORDER CREATED: {order_info} | Order ID: {order.get('id')}")
            return order
        except Exception as e:
            logger.error(f"Failed to create order: {order_info} | Error: {e}")
            return {"error": str(e)}
