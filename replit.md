# Cryptocurrency Arbitrage Bot

## Overview
A modular Python cryptocurrency arbitrage bot for cross-exchange trading with comprehensive risk management, circuit breakers, shadow trading, and automatic optimization. The bot scans multiple exchanges for price discrepancies and executes arbitrage trades when profitable opportunities are found.

## Project Architecture

### File Structure
- `main.py` - Entry point with main trading loop, heartbeat, and circuit breakers
- `config.py` - All configurable parameters (exchanges, pairs, risk limits, fees)
- `exchanges.py` - ExchangeManager class for ccxt integration
- `arbitrage.py` - Arbitrage detection and execution with per-exchange fees
- `risk.py` - RiskManager class with circuit breakers, volatility checks, and limits
- `logger.py` - Logging configuration (console + file)
- `utils.py` - Helper functions including Telegram and email alerts
- `db.py` - SQLite database for trades and system state
- `shadow.py` - Shadow trading simulation module
- `optimizer.py` - Performance analysis and dynamic parameter adjustment
- `api.py` - Flask backend for dashboard and diagnostics
- `templates/dashboard.html` - Dashboard web interface
- `static/dashboard.js` - Dashboard frontend logic
- `static/dashboard.css` - Dashboard styling
- `.env.example` - Template for API keys

### Key Features
- DRY_RUN mode for safe testing (no real orders)
- Multi-exchange support (Binance, Kraken, Bybit, OKX)
- Per-exchange fee calculation
- Dynamic minimum spread based on fees + slippage + safety margin
- Volatility checking before trading
- Circuit breakers (daily loss, API errors, trades per hour, no-data timeout)
- Heartbeat mechanism for monitoring
- Shadow trading for risk-free strategy testing
- Telegram and email alerts
- Performance optimization based on historical data
- Web dashboard with real-time stats

## Configuration

### Risk Parameters (config.py)
- `MIN_SPREAD_PERCENT`: 0.3% - Base minimum spread
- `SAFETY_MARGIN_SPREAD`: 0.15% - Additional safety buffer
- `MAX_CAPITAL_PER_TRADE_USD`: $500 - Max per trade
- `MAX_DAILY_LOSS_USD`: $1000 - Daily loss limit (circuit breaker)
- `MAX_OPEN_TRADES`: 5 - Concurrent trades limit
- `MAX_BALANCE_USAGE_PER_EXCHANGE`: 50% - Balance usage limit
- `MAX_TRADES_PER_HOUR`: 50 - Hourly trade limit
- `MAX_SYMBOL_EXPOSURE_USD`: $2000 - Max exposure per symbol
- `VOLATILITY_THRESHOLD_PERCENT`: 2.0% - Max volatility for trading

### Exchange Fees (config.py)
Per-exchange maker/taker fees are configured in `EXCHANGE_FEES` dict.

### Circuit Breakers
- Daily loss limit stops trading when exceeded
- API error limit (20 errors in 5 min) pauses trading
- Trades per hour limit prevents overtrading
- No-data timeout sends alerts when no opportunities found

### API Keys
Store in Replit Secrets or .env file:
- BINANCE_API_KEY, BINANCE_API_SECRET
- KRAKEN_API_KEY, KRAKEN_API_SECRET
- BYBIT_API_KEY, BYBIT_API_SECRET
- OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE
- Note: OKX uses hostname 'my.okx.com' for European users (configured in exchanges.py)
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (for alerts)
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL (for email alerts)

## Running the Bot

### Replit
1. Add API keys to Secrets
2. Set `DRY_RUN = True` in config.py
3. Run bot: `python main.py`
4. Run dashboard: `python api.py` (port 5000)

### VPS
1. Install: `pip install ccxt python-dotenv flask requests`
2. Create .env from .env.example
3. Run bot: `python main.py`
4. Run dashboard: `python api.py`
5. For persistence: `screen -S bot python main.py`

## Dashboard
The web dashboard is available at port 5000 when running `python api.py`.

### API Endpoints
- `GET /` - Dashboard HTML page
- `GET /api/trades/recent` - Last 100 trades
- `GET /api/stats/summary` - Overall statistics
- `GET /api/stats/daily_pnl` - Daily PNL for last 14 days
- `GET /api/health` - Health check
- `GET /api/diagnostics` - Comprehensive system diagnostics
- `GET /api/shadow/trades` - Shadow trading history
- `GET /api/shadow/stats` - Shadow trading statistics
- `GET /api/compare` - Compare real vs shadow performance

### Databases
- `trades.db` - Real trading data
- `shadow.db` - Shadow trading simulation data

## Recent Changes
- 2024-12-10: Added remote parameter editing from dashboard
- 2024-12-10: Created ParameterStore for runtime parameter management
- 2024-12-10: Added /api/params and /api/params/update endpoints
- 2024-12-10: Parameters stored in SQLite with min/max validation
- 2024-12-10: Added advanced risk management with volatility checks and orderbook depth
- 2024-12-10: Implemented circuit breakers (daily loss, API errors, trades/hour, no-data)
- 2024-12-10: Added Telegram and email alerts
- 2024-12-10: Added heartbeat mechanism for monitoring
- 2024-12-10: Created shadow trading module for risk-free testing
- 2024-12-10: Created optimizer module for performance analysis
- 2024-12-10: Added per-exchange fee calculation
- 2024-12-10: Added dynamic minimum spread calculation
- 2024-12-10: Added /api/diagnostics endpoint
- 2024-12-10: Added SQLite database for trade storage (db.py)
- 2024-12-10: Added Flask API backend with dashboard endpoints (api.py)
- 2024-12-10: Added web dashboard with Chart.js and dark theme
- 2024-12-10: Initial implementation with core modules

## Remote Parameter Editing

### Editable Parameters
The following parameters can be changed from the dashboard:
- MAX_CAPITAL_PER_TRADE_USD (1 - 10,000)
- MAX_DAILY_LOSS_USD (5 - 50,000)
- MAX_TRADES_PER_HOUR (1 - 500)
- MAX_SYMBOL_EXPOSURE_USD (10 - 100,000)
- MAX_BALANCE_USAGE_PER_EXCHANGE (0.05 - 0.9)
- MIN_SPREAD_PERCENT (0.05 - 5.0)
- VOLATILITY_THRESHOLD_PERCENT (0.5 - 10.0)
- SAFETY_MARGIN_SPREAD (0.05 - 5.0)

### How to Add New Parameters
1. Add parameter to `DEFAULT_PARAMETERS` in db.py with value, min, max, description
2. Delete trades.db or manually insert row into parameters table
3. Parameter appears automatically in dashboard

### Parameter API Endpoints
- `GET /api/params` - Get all parameters with values and ranges
- `POST /api/params/update` - Update parameter: `{"name": "PARAM_NAME", "value": 123.45}`

### Security
- Only risk/limit parameters are editable (no DRY_RUN, API keys, etc.)
- Backend validates min/max range before saving
- Parameter changes are logged

## User Preferences
- Dark theme for dashboard
- DRY_RUN mode enabled by default for safety
- Modular architecture for easy extension
