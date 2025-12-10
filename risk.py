"""
Risk management module for the arbitrage bot.
Contains decision logic, position sizing, circuit breakers, and safety checks.
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Any
from collections import deque

from logger import get_logger

logger = get_logger(__name__)

TRADING_ENABLED: bool = True
_api_errors: deque = deque()
_trades_this_hour: deque = deque()
_last_opportunity_time: float = time.time()
_last_alert_message: str = ""
_symbol_disabled_until: dict[str, datetime] = {}
_price_history: dict[str, deque] = {}


class RiskManager:
    """Manages trading risk, position sizing, circuit breakers, and limits."""

    def __init__(
        self,
        max_capital_per_trade_usd: float,
        max_daily_loss_usd: float,
        max_open_trades: int,
        max_balance_usage_per_exchange: float,
        max_trades_per_hour: int = 50,
        max_api_errors: int = 20,
        api_error_window: int = 300,
        volatility_threshold: float = 2.0,
        volatility_window: int = 10,
        max_symbol_exposure_usd: float = 2000.0
    ) -> None:
        self.max_capital_per_trade_usd = max_capital_per_trade_usd
        self.max_daily_loss_usd = max_daily_loss_usd
        self.max_open_trades = max_open_trades
        self.max_balance_usage_per_exchange = max_balance_usage_per_exchange
        self.max_trades_per_hour = max_trades_per_hour
        self.max_api_errors = max_api_errors
        self.api_error_window = api_error_window
        self.volatility_threshold = volatility_threshold
        self.volatility_window = volatility_window
        self.max_symbol_exposure_usd = max_symbol_exposure_usd
        self.current_daily_pnl_usd: float = 0.0

    def can_open_new_trade(self, open_trades_count: int) -> bool:
        """Check if a new trade can be opened based on max open trades limit."""
        if open_trades_count >= self.max_open_trades:
            logger.warning(
                f"Cannot open new trade: {open_trades_count}/{self.max_open_trades} trades already open"
            )
            return False
        return True

    def check_daily_loss_limit(self, current_daily_pnl_usd: float) -> bool:
        """
        Check if trading should continue based on daily loss limit.
        Returns True if trading is allowed, False if daily loss limit exceeded.
        """
        if current_daily_pnl_usd <= -self.max_daily_loss_usd:
            logger.error(
                f"Daily loss limit exceeded: ${current_daily_pnl_usd:.2f} "
                f"(limit: -${self.max_daily_loss_usd:.2f})"
            )
            return False
        return True

    def calculate_position_size(
        self,
        available_balance_quote: float,
        best_spread_percent: float,
        symbol: str,
        buy_price: float
    ) -> float:
        """
        Calculate the position size in base currency for a trade.
        Takes into account capital limits and balance usage restrictions.
        Scaling is applied before clamping to guarantee limits are never exceeded.
        """
        if buy_price <= 0:
            return 0.0

        max_from_capital = self.max_capital_per_trade_usd / buy_price
        max_from_balance = (available_balance_quote * self.max_balance_usage_per_exchange) / buy_price

        base_size = min(max_from_capital, max_from_balance)

        if best_spread_percent > 1.0:
            scaled_size = base_size * 1.2
        elif best_spread_percent < 0.5:
            scaled_size = base_size * 0.8
        else:
            scaled_size = base_size

        position_size = min(scaled_size, max_from_capital, max_from_balance)

        logger.debug(
            f"Position size for {symbol}: {position_size:.8f} "
            f"(max from capital: {max_from_capital:.8f}, max from balance: {max_from_balance:.8f})"
        )

        return position_size

    def dynamic_position_size(
        self,
        symbol: str,
        performance_stats: dict,
        min_size_usd: float,
        max_size_usd: float,
        buy_price: float
    ) -> float:
        """Calculate dynamic position size based on historical performance."""
        if buy_price <= 0:
            return 0.0

        win_rate = performance_stats.get("win_rate", 0.5)
        avg_pnl = performance_stats.get("avg_pnl_per_trade", 0.0)
        avg_slippage = performance_stats.get("avg_slippage", 0.0)

        score = avg_pnl * win_rate - avg_slippage

        if score < 0:
            logger.info(f"Symbol {symbol} has negative score ({score:.4f}), not trading")
            return 0.0
        elif score < 0.1:
            size_usd = min_size_usd
        elif score > 0.5:
            size_usd = max_size_usd
        else:
            ratio = (score - 0.1) / 0.4
            size_usd = min_size_usd + ratio * (max_size_usd - min_size_usd)

        return min(size_usd / buy_price, self.max_capital_per_trade_usd / buy_price)

    def is_spread_enough(self, spread_percent: float, min_spread_percent: float) -> bool:
        """Check if the spread meets the minimum requirement."""
        return spread_percent >= min_spread_percent

    def update_daily_pnl(self, pnl_change: float) -> None:
        """Update the daily PnL tracker."""
        self.current_daily_pnl_usd += pnl_change
        logger.info(f"Daily PnL updated: ${self.current_daily_pnl_usd:.2f} (change: ${pnl_change:.2f})")

    def reset_daily_pnl(self) -> None:
        """Reset daily PnL (call at start of new trading day)."""
        self.current_daily_pnl_usd = 0.0
        logger.info("Daily PnL reset to $0.00")

    def check_volatility(self, symbol: str, last_prices: list[float], threshold_percent: float) -> bool:
        """
        Check if volatility is within acceptable range.
        Returns True if safe to trade, False if volatility too high.
        """
        if len(last_prices) < 2:
            return True

        min_price = min(last_prices)
        max_price = max(last_prices)

        if min_price <= 0:
            return True

        volatility = ((max_price - min_price) / min_price) * 100

        if volatility > threshold_percent:
            logger.warning(
                f"High volatility detected for {symbol}: {volatility:.2f}% "
                f"(threshold: {threshold_percent}%)"
            )
            return False

        return True

    def check_orderbook_depth(
        self,
        buy_orderbook: dict,
        sell_orderbook: dict,
        amount_quote: float,
        max_slippage_percent: float
    ) -> bool:
        """
        Check if orderbook depth supports the trade volume without excessive slippage.
        Returns True if depth is sufficient, False otherwise.
        """
        try:
            buy_asks = buy_orderbook.get("asks", [])[:5]
            sell_bids = sell_orderbook.get("bids", [])[:5]

            if not buy_asks or not sell_bids:
                logger.warning("Insufficient orderbook data for depth check")
                return False

            total_buy_volume = sum(ask[1] * ask[0] for ask in buy_asks if len(ask) >= 2)
            total_sell_volume = sum(bid[1] * bid[0] for bid in sell_bids if len(bid) >= 2)

            if total_buy_volume < amount_quote or total_sell_volume < amount_quote:
                logger.warning(
                    f"Insufficient orderbook depth. Need ${amount_quote:.2f}, "
                    f"Buy available: ${total_buy_volume:.2f}, Sell available: ${total_sell_volume:.2f}"
                )
                return False

            if len(buy_asks) >= 2:
                best_ask = buy_asks[0][0]
                worst_ask = buy_asks[-1][0]
                buy_slippage = ((worst_ask - best_ask) / best_ask) * 100
                if buy_slippage > max_slippage_percent:
                    logger.warning(f"Buy slippage too high: {buy_slippage:.2f}%")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error checking orderbook depth: {e}")
            return True

    def limit_per_symbol(self, symbol: str, get_symbol_exposure_func) -> bool:
        """
        Check if symbol exposure is within limits.
        Returns True if can trade, False if limit exceeded.
        """
        try:
            current_exposure = get_symbol_exposure_func(symbol)
            if current_exposure >= self.max_symbol_exposure_usd:
                logger.warning(
                    f"Symbol exposure limit reached for {symbol}: "
                    f"${current_exposure:.2f} >= ${self.max_symbol_exposure_usd:.2f}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking symbol exposure: {e}")
            return True

    def should_trade_now(
        self,
        symbol: str,
        exchange_manager: Any = None,
        buy_exchange: str = "",
        sell_exchange: str = ""
    ) -> bool:
        """
        Comprehensive check if trading should proceed for a symbol.
        Returns True if all conditions are met, False otherwise.
        """
        global TRADING_ENABLED, _symbol_disabled_until

        if not TRADING_ENABLED:
            return False

        if symbol in _symbol_disabled_until:
            if datetime.utcnow() < _symbol_disabled_until[symbol]:
                logger.debug(f"Symbol {symbol} is temporarily disabled")
                return False
            else:
                del _symbol_disabled_until[symbol]

        if not self.check_daily_loss_limit(self.current_daily_pnl_usd):
            return False

        if not check_trades_per_hour_limit(self.max_trades_per_hour):
            return False

        if not check_api_error_limit(self.max_api_errors, self.api_error_window):
            return False

        if symbol in _price_history:
            prices = list(_price_history[symbol])
            if not self.check_volatility(symbol, prices, self.volatility_threshold):
                return False

        return True


def get_trading_enabled() -> bool:
    """Get current trading enabled status."""
    global TRADING_ENABLED
    return TRADING_ENABLED


def set_trading_enabled(enabled: bool, reason: str = "") -> None:
    """Set trading enabled status with logging."""
    global TRADING_ENABLED, _last_alert_message
    TRADING_ENABLED = enabled
    status = "ENABLED" if enabled else "DISABLED"
    message = f"Trading {status}"
    if reason:
        message += f": {reason}"
    logger.info(message)
    _last_alert_message = message


def record_api_error() -> None:
    """Record an API error for circuit breaker tracking."""
    global _api_errors
    _api_errors.append(time.time())


def check_api_error_limit(max_errors: int, window_seconds: int) -> bool:
    """
    Check if API errors are within acceptable limits.
    Returns True if OK, False if circuit breaker should trigger.
    """
    global _api_errors
    cutoff = time.time() - window_seconds
    _api_errors = deque([t for t in _api_errors if t > cutoff])

    if len(_api_errors) >= max_errors:
        logger.error(f"API error limit exceeded: {len(_api_errors)} errors in {window_seconds}s")
        return False
    return True


def record_trade() -> None:
    """Record a trade for hourly limit tracking."""
    global _trades_this_hour
    _trades_this_hour.append(time.time())


def check_trades_per_hour_limit(max_trades: int) -> bool:
    """
    Check if trades per hour are within limits.
    Returns True if OK, False if limit exceeded.
    """
    global _trades_this_hour
    cutoff = time.time() - 3600
    _trades_this_hour = deque([t for t in _trades_this_hour if t > cutoff])

    if len(_trades_this_hour) >= max_trades:
        logger.warning(f"Trades per hour limit reached: {len(_trades_this_hour)}/{max_trades}")
        return False
    return True


def record_opportunity_found() -> None:
    """Record that an opportunity was found (for no-data detection)."""
    global _last_opportunity_time
    _last_opportunity_time = time.time()


def check_no_data_timeout(timeout_seconds: int) -> bool:
    """
    Check if we've gone too long without finding opportunities.
    Returns True if timeout exceeded, False otherwise.
    """
    global _last_opportunity_time
    elapsed = time.time() - _last_opportunity_time
    return elapsed > timeout_seconds


def update_price_history(symbol: str, price: float, max_size: int = 10) -> None:
    """Update price history for volatility tracking."""
    global _price_history
    if symbol not in _price_history:
        _price_history[symbol] = deque(maxlen=max_size)
    _price_history[symbol].append(price)


def disable_symbol_temporarily(symbol: str, hours: int) -> None:
    """Temporarily disable trading for a symbol."""
    global _symbol_disabled_until
    _symbol_disabled_until[symbol] = datetime.utcnow() + timedelta(hours=hours)
    logger.info(f"Symbol {symbol} disabled for {hours} hours")


def get_last_alert_message() -> str:
    """Get the last alert message."""
    global _last_alert_message
    return _last_alert_message


def get_api_error_count() -> int:
    """Get current API error count in window."""
    global _api_errors
    return len(_api_errors)


def get_trades_this_hour() -> int:
    """Get number of trades in the last hour."""
    global _trades_this_hour
    cutoff = time.time() - 3600
    _trades_this_hour = deque([t for t in _trades_this_hour if t > cutoff])
    return len(_trades_this_hour)
