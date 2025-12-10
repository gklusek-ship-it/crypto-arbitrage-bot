"""
Configuration module for the cryptocurrency arbitrage bot.
All bot parameters can be modified here without touching the logic.
"""

DRY_RUN: bool = True

SUPPORTED_EXCHANGES: list[str] = ["kraken", "okx"]

TRADING_PAIRS: list[str] = ["BTC/USDT", "ETH/USDT"]

MIN_SPREAD_PERCENT: float = 0.3
TARGET_SPREAD_PERCENT: float = 0.6
MAX_SLIPPAGE_PERCENT: float = 0.15
REFRESH_INTERVAL_SECONDS: int = 5

DEFAULT_FEE_PERCENT: float = 0.1

MAX_CAPITAL_PER_TRADE_USD: float = 500.0
MAX_DAILY_LOSS_USD: float = 1000.0
MAX_OPEN_TRADES: int = 5
MAX_BALANCE_USAGE_PER_EXCHANGE: float = 0.5

LOG_TO_FILE: bool = True
LOG_FILE_NAME: str = "arbitrage_bot.log"

MAX_TRADES_PER_HOUR: int = 50
MAX_SYMBOL_EXPOSURE_USD: float = 2000.0
VOLATILITY_THRESHOLD_PERCENT: float = 2.0
VOLATILITY_WINDOW_SIZE: int = 10

HEARTBEAT_INTERVAL: int = 20
WATCHDOG_TIMEOUT: int = 90

SAFETY_MARGIN_SPREAD: float = 0.15

MAX_API_ERRORS_PER_WINDOW: int = 20
API_ERROR_WINDOW_SECONDS: int = 300

NO_DATA_ALERT_SECONDS: int = 120

EXCHANGE_FEES: dict = {
    "binance": {"maker": 0.0002, "taker": 0.0006},
    "kraken": {"maker": 0.0016, "taker": 0.0026},
    "okx": {"maker": 0.0008, "taker": 0.001},
    "bybit": {"maker": 0.0001, "taker": 0.0006},
}

SYMBOL_DISABLE_HOURS: int = 6

PARAMETER_CHANGE_LIMIT_PERCENT: float = 10.0

MIN_POSITION_SIZE_USD: float = 10.0
MAX_POSITION_SIZE_USD: float = 1000.0

SHADOW_TRADING_ENABLED: bool = True
