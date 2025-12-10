"""
Arbitrage detection and execution module.
Finds and executes cross-exchange arbitrage opportunities.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional

import config
from exchanges import ExchangeManager
from risk import RiskManager
from logger import get_logger
from utils import format_opportunity, extract_base_quote
from db import insert_trade

logger = get_logger(__name__)

open_trades: list[dict] = []
trade_history: list[dict] = []
MAX_TRADE_HISTORY: int = 100
TRADE_COOLDOWN_SECONDS: int = 60


def get_exchange_fee(exchange_id: str, fee_type: str = "taker") -> float:
    """Get the fee for an exchange from config."""
    fees = config.EXCHANGE_FEES.get(exchange_id, {"maker": 0.001, "taker": 0.001})
    return fees.get(fee_type, 0.001)


def calculate_effective_min_spread(
    buy_exchange: str,
    sell_exchange: str,
    avg_slippage: float = 0.0
) -> float:
    """
    Calculate dynamic minimum spread based on fees and slippage.
    Returns the effective minimum spread required for a profitable trade.
    """
    buy_fee = get_exchange_fee(buy_exchange, "taker") * 100
    sell_fee = get_exchange_fee(sell_exchange, "taker") * 100
    safety_margin = config.SAFETY_MARGIN_SPREAD

    effective_min = buy_fee + sell_fee + avg_slippage + safety_margin
    return effective_min


def find_arbitrage_opportunities(
    exchange_manager: ExchangeManager,
    risk_manager: RiskManager,
    trading_pairs: list[str],
    min_spread_percent: float,
    max_slippage_percent: float
) -> list[dict]:
    """
    Find arbitrage opportunities across exchanges for given trading pairs.
    Uses per-exchange fees and dynamic minimum spread calculation.
    Returns a list of opportunities that meet the minimum spread requirement.
    """
    opportunities: list[dict] = []

    for symbol in trading_pairs:
        if not risk_manager.should_trade_now(symbol):
            logger.debug(f"Skipping {symbol} - should_trade_now returned False")
            continue

        tickers: list[tuple[str, float, float]] = []

        for exchange_id in exchange_manager.exchange_ids:
            ticker = exchange_manager.get_ticker(exchange_id, symbol)
            if ticker and ticker.get("bid") and ticker.get("ask"):
                tickers.append((exchange_id, ticker["bid"], ticker["ask"]))
                from risk import update_price_history
                update_price_history(symbol, (ticker["bid"] + ticker["ask"]) / 2)

        if len(tickers) < 2:
            continue

        for i, (buy_exchange, buy_bid, buy_ask) in enumerate(tickers):
            for j, (sell_exchange, sell_bid, sell_ask) in enumerate(tickers):
                if i == j:
                    continue

                buy_price = buy_ask
                sell_price = sell_bid

                if buy_price <= 0:
                    continue

                raw_spread_percent = ((sell_price - buy_price) / buy_price) * 100

                buy_fee = get_exchange_fee(buy_exchange, "taker") * 100
                sell_fee = get_exchange_fee(sell_exchange, "taker") * 100
                total_fees_percent = buy_fee + sell_fee

                net_spread_percent = raw_spread_percent - total_fees_percent

                effective_min_spread = calculate_effective_min_spread(
                    buy_exchange, sell_exchange, max_slippage_percent
                )

                if net_spread_percent >= effective_min_spread:
                    opportunity = {
                        "symbol": symbol,
                        "buy_exchange_id": buy_exchange,
                        "sell_exchange_id": sell_exchange,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "raw_spread_percent": raw_spread_percent,
                        "net_spread_percent": net_spread_percent,
                        "buy_fee_percent": buy_fee,
                        "sell_fee_percent": sell_fee,
                        "effective_min_spread": effective_min_spread,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    opportunities.append(opportunity)
                    logger.info(f"Opportunity found: {format_opportunity(opportunity)}")
                    from risk import record_opportunity_found
                    record_opportunity_found()

    return opportunities


def execute_arbitrage_opportunity(
    exchange_manager: ExchangeManager,
    risk_manager: RiskManager,
    opportunity: dict,
    balances: dict,
    conf: Any
) -> Optional[dict]:
    """
    Execute an arbitrage opportunity by placing buy and sell orders.
    Returns trade info if successful, None otherwise.
    """
    symbol = opportunity["symbol"]
    buy_exchange = opportunity["buy_exchange_id"]
    sell_exchange = opportunity["sell_exchange_id"]
    buy_price = opportunity["buy_price"]
    sell_price = opportunity["sell_price"]
    net_spread = opportunity["net_spread_percent"]

    base, quote = extract_base_quote(symbol)
    if not base or not quote:
        logger.error(f"Invalid symbol format: {symbol}")
        return None

    buy_balance = balances.get(buy_exchange, {})
    sell_balance = balances.get(sell_exchange, {})

    quote_available = buy_balance.get(quote, 0.0)
    base_available = sell_balance.get(base, 0.0)

    if quote_available <= 0:
        logger.warning(f"Insufficient {quote} balance on {buy_exchange}")
        return None

    position_size = risk_manager.calculate_position_size(
        available_balance_quote=quote_available,
        best_spread_percent=net_spread,
        symbol=symbol,
        buy_price=buy_price
    )

    if position_size <= 0:
        logger.warning("Calculated position size is zero or negative")
        return None

    if base_available < position_size:
        position_size = base_available
        if position_size <= 0:
            logger.warning(f"Insufficient {base} balance on {sell_exchange} to sell")
            return None

    slippage_adjusted_spread = net_spread - conf.MAX_SLIPPAGE_PERCENT
    if slippage_adjusted_spread < conf.MIN_SPREAD_PERCENT:
        logger.warning(
            f"Spread after slippage ({slippage_adjusted_spread:.3f}%) below minimum ({conf.MIN_SPREAD_PERCENT}%)"
        )
        return None

    logger.info(
        f"Executing arbitrage: BUY {position_size:.8f} {base} on {buy_exchange} @ {buy_price:.2f} | "
        f"SELL on {sell_exchange} @ {sell_price:.2f}"
    )

    trade_id = f"{symbol}_{buy_exchange}_{sell_exchange}_{datetime.utcnow().timestamp()}"
    pending_trade = {
        "id": trade_id,
        "symbol": symbol,
        "buy_exchange": buy_exchange,
        "sell_exchange": sell_exchange,
        "position_size": position_size,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "pending"
    }
    open_trades.append(pending_trade)

    try:
        buy_order = exchange_manager.create_order(
            exchange_id=buy_exchange,
            symbol=symbol,
            side="buy",
            order_type="market",
            amount=position_size,
            price=None
        )
    except Exception as e:
        logger.error(f"Buy order exception: {e}")
        _mark_trade_failed_and_prune(trade_id, "buy_exception", {"error": str(e)})
        return None

    if buy_order.get("error"):
        logger.error(f"Buy order failed: {buy_order.get('error')}")
        _mark_trade_failed_and_prune(trade_id, "buy_failed", buy_order)
        return None

    try:
        sell_order = exchange_manager.create_order(
            exchange_id=sell_exchange,
            symbol=symbol,
            side="sell",
            order_type="market",
            amount=position_size,
            price=None
        )
    except Exception as e:
        logger.error(f"Sell order exception: {e}")
        _mark_trade_failed_and_prune(trade_id, "sell_exception", {"error": str(e)}, buy_order)
        return None

    if sell_order.get("error"):
        logger.error(f"Sell order failed: {sell_order.get('error')}")
        _mark_trade_failed_and_prune(trade_id, "sell_failed", sell_order, buy_order)
        return None

    estimated_cost = position_size * buy_price
    estimated_revenue = position_size * sell_price
    estimated_profit = estimated_revenue - estimated_cost
    fee_cost = (estimated_cost + estimated_revenue) * (conf.DEFAULT_FEE_PERCENT / 100)
    net_profit = estimated_profit - fee_cost

    executed_trade = _complete_trade_and_archive(trade_id, buy_order, sell_order, net_profit)

    if executed_trade:
        logger.info(
            f"Trade executed: Bought {position_size:.8f} {base} @ {buy_price:.2f} on {buy_exchange} | "
            f"Sold @ {sell_price:.2f} on {sell_exchange} | "
            f"Est. net profit: ${net_profit:.2f}"
        )
        risk_manager.update_daily_pnl(net_profit)

    return executed_trade


def _mark_trade_failed_and_prune(trade_id: str, failure_reason: str, failed_order: dict, successful_order: Optional[dict] = None) -> None:
    """Mark a trade as failed and immediately archive it to history."""
    global open_trades
    
    trade_to_archive = None
    for trade in open_trades:
        if trade.get("id") == trade_id:
            trade["status"] = "failed"
            trade["failure_reason"] = failure_reason
            trade["failed_order"] = failed_order
            if successful_order:
                trade["partial_order"] = successful_order
            trade["completed_at"] = datetime.utcnow().isoformat()
            trade_to_archive = trade
            logger.warning(f"Trade {trade_id} marked as failed: {failure_reason}")
            break
    
    if trade_to_archive:
        open_trades = [t for t in open_trades if t.get("id") != trade_id]
        trade_history.append(trade_to_archive)
        if len(trade_history) > MAX_TRADE_HISTORY:
            trade_history.pop(0)


def _complete_trade_and_archive(trade_id: str, buy_order: dict, sell_order: dict, net_profit: float) -> Optional[dict]:
    """Mark trade as completed, save to database, and archive to history."""
    global open_trades
    
    executed_trade = None
    for trade in open_trades:
        if trade.get("id") == trade_id:
            trade["status"] = "completed"
            trade["buy_order"] = buy_order
            trade["sell_order"] = sell_order
            trade["estimated_profit_usd"] = net_profit
            trade["completed_at"] = datetime.utcnow().isoformat()
            executed_trade = trade
            break
    
    if executed_trade:
        open_trades = [t for t in open_trades if t.get("id") != trade_id]
        trade_history.append(executed_trade)
        if len(trade_history) > MAX_TRADE_HISTORY:
            trade_history.pop(0)
        
        try:
            buy_price = executed_trade.get("buy_price", 0)
            sell_price = executed_trade.get("sell_price", 0)
            amount = executed_trade.get("position_size", 0)
            estimated_cost = amount * buy_price
            estimated_revenue = amount * sell_price
            fee_cost = (estimated_cost + estimated_revenue) * (config.DEFAULT_FEE_PERCENT / 100)
            
            raw_spread = ((sell_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
            net_spread = raw_spread - (config.DEFAULT_FEE_PERCENT * 2)
            
            trade_record = {
                "timestamp": executed_trade.get("completed_at", datetime.utcnow().isoformat()),
                "symbol": executed_trade.get("symbol", ""),
                "buy_exchange": executed_trade.get("buy_exchange", ""),
                "sell_exchange": executed_trade.get("sell_exchange", ""),
                "buy_price": buy_price,
                "sell_price": sell_price,
                "amount": amount,
                "gross_spread_percent": raw_spread,
                "net_spread_percent": net_spread,
                "fees_estimated": fee_cost,
                "pnl_usd": net_profit,
                "dry_run": 1 if config.DRY_RUN else 0,
                "extra_info": json.dumps({
                    "buy_order": buy_order,
                    "sell_order": sell_order,
                    "trade_id": trade_id
                })
            }
            insert_trade(trade_record)
            logger.debug(f"Trade {trade_id} saved to database")
        except Exception as e:
            logger.error(f"Failed to save trade to database: {e}")
    
    return executed_trade


def prune_completed_trades() -> None:
    """Move completed/failed trades from open_trades to trade_history immediately."""
    global open_trades
    
    trades_to_archive = []
    remaining_trades = []
    
    for trade in open_trades:
        status = trade.get("status")
        if status in ("completed", "failed"):
            trades_to_archive.append(trade)
        else:
            remaining_trades.append(trade)
    
    for trade in trades_to_archive:
        trade_history.append(trade)
        if len(trade_history) > MAX_TRADE_HISTORY:
            trade_history.pop(0)
    
    open_trades = remaining_trades
    
    if trades_to_archive:
        logger.debug(f"Archived {len(trades_to_archive)} trades to history")


def get_open_trades() -> list[dict]:
    """Return the list of currently pending trades (not yet completed)."""
    return [t for t in open_trades if t.get("status") == "pending"]


def get_open_trades_count() -> int:
    """Return the count of currently active trades."""
    return len(get_open_trades())


def clear_open_trades() -> None:
    """Clear the open trades list."""
    global open_trades
    open_trades = []


def get_trade_history() -> list[dict]:
    """Return the trade history list."""
    return trade_history


def clear_trade_history() -> None:
    """Clear the trade history."""
    global trade_history
    trade_history = []
