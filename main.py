"""
Cryptocurrency Arbitrage Bot - Main Entry Point

=== HOW TO RUN ===

On Replit:
1. Add your API keys to Secrets (or create a .env file):
   - BINANCE_API_KEY, BINANCE_API_SECRET
   - KRAKEN_API_KEY, KRAKEN_API_SECRET
   - BYBIT_API_KEY, BYBIT_API_SECRET
   - OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE
   - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (for alerts)
2. Set DRY_RUN = True in config.py for testing (default)
3. Click Run or execute: python main.py

On VPS:
1. Clone/copy the project files
2. Install dependencies: pip install ccxt python-dotenv flask
3. Create a .env file with your API keys (see utils.py for format)
4. Set DRY_RUN = True in config.py for testing
5. Run: python main.py
6. Use screen/tmux for persistent sessions: screen -S bot python main.py

=== SECURITY NOTES ===
- Always start with DRY_RUN = True
- Use API keys with trading permissions only (no withdrawals)
- Monitor the bot regularly
- Set reasonable risk parameters in config.py
"""

import time
import sys

import config
from exchanges import ExchangeManager
from risk import (
    RiskManager, 
    get_trading_enabled, 
    set_trading_enabled,
    record_api_error,
    check_api_error_limit,
    record_trade,
    check_no_data_timeout,
    get_api_error_count,
    get_trades_this_hour
)
from arbitrage import find_arbitrage_opportunities, execute_arbitrage_opportunity, get_open_trades_count, prune_completed_trades
from logger import setup_logging, get_logger
from utils import load_env, send_alert
from db import init_db, update_heartbeat, init_parameters
from shadow import init_shadow_db, simulate_arbitrage, insert_shadow_trade
from param_store import get_store, maybe_reload_params


def main() -> None:
    """Main entry point for the arbitrage bot."""
    load_env()

    setup_logging(
        log_to_file=config.LOG_TO_FILE,
        log_file_name=config.LOG_FILE_NAME
    )
    logger = get_logger(__name__)

    init_db()
    init_shadow_db()
    init_parameters()
    
    param_store = get_store()
    logger.info(f"Databases initialized, {len(param_store.get_all())} parameters loaded")

    send_alert("Arbitrage Bot Starting", "Bot Startup")

    logger.info("=" * 60)
    logger.info("Cryptocurrency Arbitrage Bot Starting")
    logger.info(f"DRY_RUN mode: {config.DRY_RUN}")
    logger.info(f"Exchanges: {config.SUPPORTED_EXCHANGES}")
    logger.info(f"Trading pairs: {config.TRADING_PAIRS}")
    logger.info(f"Min spread: {config.MIN_SPREAD_PERCENT}%")
    logger.info(f"Max capital per trade: ${config.MAX_CAPITAL_PER_TRADE_USD}")
    logger.info(f"Max trades per hour: {config.MAX_TRADES_PER_HOUR}")
    logger.info(f"Heartbeat interval: {config.HEARTBEAT_INTERVAL}s")
    logger.info("=" * 60)

    exchange_manager = ExchangeManager(config.SUPPORTED_EXCHANGES)

    logger.info("Loading markets from exchanges...")
    exchange_manager.load_markets()

    risk_manager = RiskManager(
        max_capital_per_trade_usd=param_store.get_param("MAX_CAPITAL_PER_TRADE_USD", config.MAX_CAPITAL_PER_TRADE_USD),
        max_daily_loss_usd=param_store.get_param("MAX_DAILY_LOSS_USD", config.MAX_DAILY_LOSS_USD),
        max_open_trades=config.MAX_OPEN_TRADES,
        max_balance_usage_per_exchange=param_store.get_param("MAX_BALANCE_USAGE_PER_EXCHANGE", config.MAX_BALANCE_USAGE_PER_EXCHANGE),
        max_trades_per_hour=int(param_store.get_param("MAX_TRADES_PER_HOUR", config.MAX_TRADES_PER_HOUR)),
        max_api_errors=config.MAX_API_ERRORS_PER_WINDOW,
        api_error_window=config.API_ERROR_WINDOW_SECONDS,
        volatility_threshold=param_store.get_param("VOLATILITY_THRESHOLD_PERCENT", config.VOLATILITY_THRESHOLD_PERCENT),
        volatility_window=config.VOLATILITY_WINDOW_SIZE,
        max_symbol_exposure_usd=param_store.get_param("MAX_SYMBOL_EXPOSURE_USD", config.MAX_SYMBOL_EXPOSURE_USD)
    )

    balance_refresh_counter = 0
    balance_refresh_interval = 6
    balances: dict[str, dict] = {}
    loop_counter = 0
    last_heartbeat_time = time.time()
    no_data_alert_sent = False

    logger.info("Starting main trading loop...")

    try:
        while True:
            loop_counter += 1
            prune_completed_trades()

            if time.time() - last_heartbeat_time >= config.HEARTBEAT_INTERVAL:
                update_heartbeat()
                last_heartbeat_time = time.time()
                logger.debug("Heartbeat updated")
            
            maybe_reload_params()
            risk_manager.max_capital_per_trade_usd = param_store.get_param("MAX_CAPITAL_PER_TRADE_USD", config.MAX_CAPITAL_PER_TRADE_USD)
            risk_manager.max_daily_loss_usd = param_store.get_param("MAX_DAILY_LOSS_USD", config.MAX_DAILY_LOSS_USD)
            risk_manager.max_trades_per_hour = int(param_store.get_param("MAX_TRADES_PER_HOUR", config.MAX_TRADES_PER_HOUR))
            risk_manager.max_symbol_exposure_usd = param_store.get_param("MAX_SYMBOL_EXPOSURE_USD", config.MAX_SYMBOL_EXPOSURE_USD)
            risk_manager.volatility_threshold = param_store.get_param("VOLATILITY_THRESHOLD_PERCENT", config.VOLATILITY_THRESHOLD_PERCENT)

            if not check_api_error_limit(config.MAX_API_ERRORS_PER_WINDOW, config.API_ERROR_WINDOW_SECONDS):
                set_trading_enabled(False, "API error limit exceeded")
                send_alert(
                    f"Trading disabled due to {get_api_error_count()} API errors in {config.API_ERROR_WINDOW_SECONDS}s",
                    "Circuit Breaker Triggered"
                )
                time.sleep(60)
                continue

            if not get_trading_enabled():
                logger.debug("Trading disabled, skipping loop")
                time.sleep(config.REFRESH_INTERVAL_SECONDS)
                continue

            if balance_refresh_counter % balance_refresh_interval == 0:
                logger.debug("Refreshing balances from exchanges...")
                for exchange_id in config.SUPPORTED_EXCHANGES:
                    try:
                        balances[exchange_id] = exchange_manager.get_balances(exchange_id)
                    except Exception as e:
                        logger.error(f"Error fetching balances from {exchange_id}: {e}")
                        record_api_error()
                balance_refresh_counter = 0

            balance_refresh_counter += 1

            if not risk_manager.check_daily_loss_limit(risk_manager.current_daily_pnl_usd):
                set_trading_enabled(False, "Daily loss limit exceeded")
                send_alert(
                    f"Daily loss limit exceeded: ${risk_manager.current_daily_pnl_usd:.2f}",
                    "Circuit Breaker - Daily Loss"
                )
                logger.info("Bot entering read-only mode. Restart tomorrow to resume trading.")
                break

            current_min_spread = param_store.get_param("MIN_SPREAD_PERCENT", config.MIN_SPREAD_PERCENT)
            
            opportunities = find_arbitrage_opportunities(
                exchange_manager=exchange_manager,
                risk_manager=risk_manager,
                trading_pairs=config.TRADING_PAIRS,
                min_spread_percent=current_min_spread,
                max_slippage_percent=config.MAX_SLIPPAGE_PERCENT
            )

            if check_no_data_timeout(config.NO_DATA_ALERT_SECONDS):
                if not no_data_alert_sent:
                    logger.warning(f"No opportunities found for {config.NO_DATA_ALERT_SECONDS}s")
                    send_alert(
                        f"No trading opportunities found for {config.NO_DATA_ALERT_SECONDS} seconds",
                        "No Data Alert"
                    )
                    no_data_alert_sent = True
            else:
                no_data_alert_sent = False

            if config.SHADOW_TRADING_ENABLED:
                for opp in opportunities:
                    shadow_result = simulate_arbitrage(opp, balances, config)
                    if shadow_result:
                        insert_shadow_trade(shadow_result)

            executed_count = 0

            for opportunity in opportunities:
                current_open_trades = get_open_trades_count()
                if not risk_manager.can_open_new_trade(current_open_trades):
                    logger.info("Max open trades reached, skipping remaining opportunities")
                    break

                if get_trades_this_hour() >= config.MAX_TRADES_PER_HOUR:
                    logger.warning("Max trades per hour reached, entering read-only mode")
                    break

                result = execute_arbitrage_opportunity(
                    exchange_manager=exchange_manager,
                    risk_manager=risk_manager,
                    opportunity=opportunity,
                    balances=balances,
                    conf=config
                )

                if result:
                    executed_count += 1
                    record_trade()

            logger.info(
                f"Loop #{loop_counter}: Found {len(opportunities)} opportunities, "
                f"executed {executed_count} trades, "
                f"daily PnL: ${risk_manager.current_daily_pnl_usd:.2f}, "
                f"trades/hour: {get_trades_this_hour()}"
            )

            time.sleep(config.REFRESH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
        logger.info(f"Final daily PnL: ${risk_manager.current_daily_pnl_usd:.2f}")
        send_alert(
            f"Bot stopped. Final PnL: ${risk_manager.current_daily_pnl_usd:.2f}",
            "Bot Shutdown"
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        send_alert(f"Bot crashed with error: {e}", "Bot Error")
        raise


if __name__ == "__main__":
    main()
