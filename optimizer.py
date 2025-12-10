"""
Automatic optimization module for the arbitrage bot.
Analyzes performance and adjusts parameters dynamically.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from logger import get_logger
import config

logger = get_logger(__name__)

DEFAULT_DB_PATH = "trades.db"


def init_parameters_table(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize the parameters table for dynamic configuration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parameters (
            param_name TEXT PRIMARY KEY,
            value REAL NOT NULL,
            min_value REAL,
            max_value REAL,
            updated_at TEXT NOT NULL,
            updated_by TEXT DEFAULT 'system',
            previous_value REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            buy_exchange TEXT,
            sell_exchange TEXT,
            avg_pnl REAL,
            win_rate REAL,
            trade_count INTEGER,
            avg_slippage REAL,
            score REAL,
            computed_at TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parameter_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            param_name TEXT NOT NULL,
            old_value REAL,
            new_value REAL,
            changed_at TEXT NOT NULL,
            changed_by TEXT,
            reason TEXT
        )
    ''')

    conn.commit()
    conn.close()


def get_parameter(param_name: str, default: float, db_path: str = DEFAULT_DB_PATH) -> float:
    """Get a parameter value from the database, or return default."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM parameters WHERE param_name = ?', (param_name,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception as e:
        logger.debug(f"Error getting parameter {param_name}: {e}")
        return default


def set_parameter(
    param_name: str,
    value: float,
    updated_by: str = "optimizer",
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    db_path: str = DEFAULT_DB_PATH
) -> bool:
    """Set a parameter value in the database with change tracking."""
    try:
        init_parameters_table(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT value FROM parameters WHERE param_name = ?', (param_name,))
        row = cursor.fetchone()
        old_value = row[0] if row else None

        if old_value is not None:
            max_change = abs(old_value) * (config.PARAMETER_CHANGE_LIMIT_PERCENT / 100)
            if abs(value - old_value) > max_change:
                if value > old_value:
                    value = old_value + max_change
                else:
                    value = old_value - max_change
                logger.warning(f"Parameter change limited: {param_name} capped at {value:.4f}")

        now = datetime.utcnow().isoformat()

        cursor.execute('''
            INSERT INTO parameters (param_name, value, min_value, max_value, updated_at, updated_by, previous_value)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(param_name) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by,
                previous_value = parameters.value
        ''', (param_name, value, min_value, max_value, now, updated_by, old_value))

        cursor.execute('''
            INSERT INTO parameter_history (param_name, old_value, new_value, changed_at, changed_by, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (param_name, old_value, value, now, updated_by, "automatic_optimization"))

        conn.commit()
        conn.close()

        logger.info(f"Parameter updated: {param_name} = {value:.4f} (was {old_value})")
        return True
    except Exception as e:
        logger.error(f"Error setting parameter {param_name}: {e}")
        return False


def compute_pair_performance(symbol: str, days: int = 14, db_path: str = DEFAULT_DB_PATH) -> dict:
    """Compute performance statistics for a trading pair."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute('''
            SELECT 
                COUNT(*) as trade_count,
                COALESCE(AVG(pnl_usd), 0) as avg_pnl,
                COALESCE(AVG(net_spread_percent), 0) as avg_spread,
                COALESCE(MAX(pnl_usd), 0) as best_pnl,
                COALESCE(MIN(pnl_usd), 0) as worst_pnl,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE symbol = ? AND timestamp >= ?
        ''', (symbol, start_date))

        row = cursor.fetchone()
        conn.close()

        trade_count = row[0] or 0
        wins = row[5] or 0
        win_rate = (wins / trade_count) if trade_count > 0 else 0.5

        return {
            "symbol": symbol,
            "trade_count": trade_count,
            "avg_pnl_per_trade": round(row[1] or 0, 4),
            "avg_spread": round(row[2] or 0, 4),
            "best_pnl": round(row[3] or 0, 2),
            "worst_pnl": round(row[4] or 0, 2),
            "win_rate": round(win_rate, 4),
            "avg_slippage": 0.0
        }
    except Exception as e:
        logger.error(f"Error computing pair performance for {symbol}: {e}")
        return {"symbol": symbol, "trade_count": 0, "win_rate": 0.5, "avg_pnl_per_trade": 0}


def compute_exchange_pair_performance(
    buy_exchange: str,
    sell_exchange: str,
    days: int = 14,
    db_path: str = DEFAULT_DB_PATH
) -> dict:
    """Compute performance statistics for an exchange pair."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute('''
            SELECT 
                COUNT(*) as trade_count,
                COALESCE(AVG(pnl_usd), 0) as avg_pnl,
                COALESCE(SUM(fees_estimated), 0) as total_fees,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE buy_exchange = ? AND sell_exchange = ? AND timestamp >= ?
        ''', (buy_exchange, sell_exchange, start_date))

        row = cursor.fetchone()
        conn.close()

        trade_count = row[0] or 0
        wins = row[3] or 0
        win_rate = (wins / trade_count) if trade_count > 0 else 0.5

        return {
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "trade_count": trade_count,
            "avg_pnl": round(row[1] or 0, 4),
            "total_fees": round(row[2] or 0, 2),
            "win_rate": round(win_rate, 4)
        }
    except Exception as e:
        logger.error(f"Error computing exchange pair performance: {e}")
        return {"buy_exchange": buy_exchange, "sell_exchange": sell_exchange, "trade_count": 0}


def save_performance_score(
    symbol: str,
    buy_exchange: str,
    sell_exchange: str,
    stats: dict,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    """Save performance score to database."""
    try:
        init_parameters_table(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        score = (stats.get("avg_pnl_per_trade", 0) * stats.get("win_rate", 0.5) 
                 - stats.get("avg_slippage", 0))

        cursor.execute('''
            INSERT INTO performance_scores 
            (symbol, buy_exchange, sell_exchange, avg_pnl, win_rate, trade_count, avg_slippage, score, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol, buy_exchange, sell_exchange,
            stats.get("avg_pnl_per_trade", 0),
            stats.get("win_rate", 0.5),
            stats.get("trade_count", 0),
            stats.get("avg_slippage", 0),
            score,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving performance score: {e}")


def compare_shadow_vs_real(days: int = 7, db_path: str = DEFAULT_DB_PATH, shadow_db_path: str = "shadow.db") -> dict:
    """Compare shadow trading results with real trading results."""
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        conn_real = sqlite3.connect(db_path)
        cursor_real = conn_real.cursor()
        cursor_real.execute('''
            SELECT 
                COUNT(*) as trade_count,
                COALESCE(AVG(pnl_usd), 0) as avg_pnl,
                COALESCE(SUM(pnl_usd), 0) as total_pnl,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE timestamp >= ?
        ''', (start_date,))
        real_row = cursor_real.fetchone()
        conn_real.close()

        conn_shadow = sqlite3.connect(shadow_db_path)
        cursor_shadow = conn_shadow.cursor()
        cursor_shadow.execute('''
            SELECT 
                COUNT(*) as trade_count,
                COALESCE(AVG(pnl_usd), 0) as avg_pnl,
                COALESCE(SUM(pnl_usd), 0) as total_pnl,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins
            FROM shadow_trades
            WHERE timestamp >= ?
        ''', (start_date,))
        shadow_row = cursor_shadow.fetchone()
        conn_shadow.close()

        real_trades = real_row[0] or 0
        shadow_trades = shadow_row[0] or 0

        return {
            "real": {
                "trade_count": real_trades,
                "avg_pnl": round(real_row[1] or 0, 4),
                "total_pnl": round(real_row[2] or 0, 2),
                "win_rate": round((real_row[3] or 0) / real_trades, 4) if real_trades > 0 else 0
            },
            "shadow": {
                "trade_count": shadow_trades,
                "avg_pnl": round(shadow_row[1] or 0, 4),
                "total_pnl": round(shadow_row[2] or 0, 2),
                "win_rate": round((shadow_row[3] or 0) / shadow_trades, 4) if shadow_trades > 0 else 0
            },
            "shadow_better": (shadow_row[1] or 0) > (real_row[1] or 0)
        }
    except Exception as e:
        logger.error(f"Error comparing shadow vs real: {e}")
        return {"real": {}, "shadow": {}, "shadow_better": False}


def run_daily_optimization(db_path: str = DEFAULT_DB_PATH) -> dict:
    """Run daily optimization to adjust parameters based on performance."""
    try:
        init_parameters_table(db_path)
        results = {}

        comparison = compare_shadow_vs_real(days=7, db_path=db_path)
        results["comparison"] = comparison

        for symbol in config.TRADING_PAIRS:
            stats = compute_pair_performance(symbol, days=7, db_path=db_path)
            results[symbol] = stats

            if stats.get("trade_count", 0) >= 10:
                if stats.get("win_rate", 0.5) < 0.4:
                    logger.warning(f"Symbol {symbol} has low win rate, consider disabling")

        return results
    except Exception as e:
        logger.error(f"Error running daily optimization: {e}")
        return {}
