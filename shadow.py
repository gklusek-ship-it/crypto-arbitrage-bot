"""
Shadow trading module for risk-free strategy simulation.
Simulates trades without executing real orders.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from logger import get_logger
import config

logger = get_logger(__name__)

SHADOW_DB_PATH = "shadow.db"


def init_shadow_db(db_path: str = SHADOW_DB_PATH) -> None:
    """Initialize the shadow trading database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shadow_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            buy_exchange TEXT NOT NULL,
            sell_exchange TEXT NOT NULL,
            buy_price REAL NOT NULL,
            sell_price REAL NOT NULL,
            amount REAL NOT NULL,
            gross_spread_percent REAL,
            net_spread_percent REAL,
            fees_estimated REAL,
            pnl_usd REAL NOT NULL,
            slippage_estimated REAL,
            strategy_params TEXT,
            extra_info TEXT
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_shadow_timestamp 
        ON shadow_trades(timestamp DESC)
    ''')

    conn.commit()
    conn.close()
    logger.debug("Shadow database initialized")


def simulate_arbitrage(
    opportunity: dict,
    balances: dict,
    conf: Any,
    position_size: Optional[float] = None
) -> Optional[dict]:
    """
    Simulate an arbitrage trade without executing real orders.
    Returns a dict with hypothetical results or None if simulation fails.
    """
    symbol = opportunity.get("symbol", "")
    buy_exchange = opportunity.get("buy_exchange_id", "")
    sell_exchange = opportunity.get("sell_exchange_id", "")
    buy_price = opportunity.get("buy_price", 0)
    sell_price = opportunity.get("sell_price", 0)
    raw_spread = opportunity.get("raw_spread_percent", 0)
    net_spread = opportunity.get("net_spread_percent", 0)

    if buy_price <= 0 or sell_price <= 0:
        return None

    if position_size is None:
        position_size = conf.MAX_CAPITAL_PER_TRADE_USD / buy_price

    buy_fee_rate = config.EXCHANGE_FEES.get(buy_exchange, {}).get("taker", 0.001)
    sell_fee_rate = config.EXCHANGE_FEES.get(sell_exchange, {}).get("taker", 0.001)

    estimated_cost = position_size * buy_price
    estimated_revenue = position_size * sell_price

    buy_fee = estimated_cost * buy_fee_rate
    sell_fee = estimated_revenue * sell_fee_rate
    total_fees = buy_fee + sell_fee

    estimated_slippage = (estimated_cost + estimated_revenue) * (conf.MAX_SLIPPAGE_PERCENT / 100) / 2

    gross_profit = estimated_revenue - estimated_cost
    net_profit = gross_profit - total_fees - estimated_slippage

    shadow_trade = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "buy_exchange": buy_exchange,
        "sell_exchange": sell_exchange,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "amount": position_size,
        "gross_spread_percent": raw_spread,
        "net_spread_percent": net_spread,
        "fees_estimated": total_fees,
        "pnl_usd": net_profit,
        "slippage_estimated": estimated_slippage,
        "strategy_params": json.dumps({
            "buy_fee_rate": buy_fee_rate,
            "sell_fee_rate": sell_fee_rate,
            "max_slippage": conf.MAX_SLIPPAGE_PERCENT,
            "min_spread": conf.MIN_SPREAD_PERCENT
        }),
        "extra_info": json.dumps({
            "opportunity": opportunity,
            "position_size_usd": estimated_cost
        })
    }

    return shadow_trade


def insert_shadow_trade(record: dict, db_path: str = SHADOW_DB_PATH) -> None:
    """Insert a shadow trade record into the database."""
    init_shadow_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO shadow_trades (
            timestamp, symbol, buy_exchange, sell_exchange,
            buy_price, sell_price, amount,
            gross_spread_percent, net_spread_percent,
            fees_estimated, pnl_usd, slippage_estimated,
            strategy_params, extra_info
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        record.get("timestamp", datetime.utcnow().isoformat()),
        record.get("symbol", ""),
        record.get("buy_exchange", ""),
        record.get("sell_exchange", ""),
        record.get("buy_price", 0.0),
        record.get("sell_price", 0.0),
        record.get("amount", 0.0),
        record.get("gross_spread_percent"),
        record.get("net_spread_percent"),
        record.get("fees_estimated"),
        record.get("pnl_usd", 0.0),
        record.get("slippage_estimated"),
        record.get("strategy_params"),
        record.get("extra_info")
    ))

    conn.commit()
    conn.close()
    logger.debug(f"Shadow trade saved: {record.get('symbol')} PnL: ${record.get('pnl_usd', 0):.2f}")


def get_shadow_trades(limit: int = 100, db_path: str = SHADOW_DB_PATH) -> list:
    """Get recent shadow trades."""
    try:
        init_shadow_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM shadow_trades
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        trades = [dict(row) for row in rows]
        conn.close()
        return trades
    except Exception as e:
        logger.error(f"Error getting shadow trades: {e}")
        return []


def get_shadow_stats(days: int = 7, db_path: str = SHADOW_DB_PATH) -> dict:
    """Get shadow trading statistics."""
    try:
        init_shadow_db(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                COALESCE(SUM(pnl_usd), 0) as total_pnl_usd,
                COALESCE(AVG(pnl_usd), 0) as avg_pnl_per_trade,
                COALESCE(MAX(pnl_usd), 0) as best_trade_pnl,
                COALESCE(MIN(pnl_usd), 0) as worst_trade_pnl,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades
            FROM shadow_trades
            WHERE timestamp >= datetime('now', ?)
        ''', (f'-{days} days',))

        row = cursor.fetchone()
        conn.close()

        total_trades = row[0] or 0
        winning_trades = row[5] or 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "total_pnl_usd": round(row[1] or 0, 2),
            "avg_pnl_per_trade": round(row[2] or 0, 2),
            "best_trade_pnl": round(row[3] or 0, 2),
            "worst_trade_pnl": round(row[4] or 0, 2),
            "win_rate": round(win_rate, 1)
        }
    except Exception as e:
        logger.error(f"Error getting shadow stats: {e}")
        return {}
