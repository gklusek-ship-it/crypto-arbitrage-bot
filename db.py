"""
Database module for storing arbitrage trades in SQLite.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

DEFAULT_DB_PATH = "trades.db"


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
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
            dry_run INTEGER NOT NULL DEFAULT 1,
            extra_info TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trades_timestamp 
        ON trades(timestamp DESC)
    ''')
    
    conn.commit()
    conn.close()


def insert_trade(trade: dict, db_path: str = DEFAULT_DB_PATH) -> None:
    """Insert a trade record into the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO trades (
            timestamp, symbol, buy_exchange, sell_exchange,
            buy_price, sell_price, amount,
            gross_spread_percent, net_spread_percent,
            fees_estimated, pnl_usd, dry_run, extra_info
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        trade.get("timestamp", datetime.utcnow().isoformat()),
        trade.get("symbol", ""),
        trade.get("buy_exchange", ""),
        trade.get("sell_exchange", ""),
        trade.get("buy_price", 0.0),
        trade.get("sell_price", 0.0),
        trade.get("amount", 0.0),
        trade.get("gross_spread_percent"),
        trade.get("net_spread_percent"),
        trade.get("fees_estimated"),
        trade.get("pnl_usd", 0.0),
        trade.get("dry_run", 1),
        trade.get("extra_info")
    ))
    
    conn.commit()
    conn.close()


def get_recent_trades(limit: int = 100, db_path: str = DEFAULT_DB_PATH) -> list:
    """Get the most recent trades."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM trades
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    trades = [dict(row) for row in rows]
    
    conn.close()
    return trades


def get_pnl_summary(days: int = 7, db_path: str = DEFAULT_DB_PATH) -> list:
    """Get daily PNL summary for the last N days."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor.execute('''
        SELECT 
            DATE(timestamp) as date,
            SUM(pnl_usd) as total_pnl,
            COUNT(*) as trade_count,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END) as losing_trades
        FROM trades
        WHERE DATE(timestamp) >= ?
        GROUP BY DATE(timestamp)
        ORDER BY DATE(timestamp) ASC
    ''', (start_date,))
    
    rows = cursor.fetchall()
    summary = [dict(row) for row in rows]
    
    conn.close()
    return summary


def get_overall_stats(db_path: str = DEFAULT_DB_PATH) -> dict:
    """Get overall trading statistics."""
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
        FROM trades
    ''')
    
    row = cursor.fetchone()
    
    total_trades = row[0] or 0
    winning_trades = row[5] or 0
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    stats = {
        "total_trades": total_trades,
        "total_pnl_usd": round(row[1] or 0, 2),
        "avg_pnl_per_trade": round(row[2] or 0, 2),
        "best_trade_pnl": round(row[3] or 0, 2),
        "worst_trade_pnl": round(row[4] or 0, 2),
        "win_rate": round(win_rate, 1)
    }
    
    conn.close()
    return stats


def init_system_state_table(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize system state table for heartbeat and status tracking."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()


def update_heartbeat(db_path: str = DEFAULT_DB_PATH) -> None:
    """Update the heartbeat timestamp."""
    init_system_state_table(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now = datetime.utcnow().isoformat()
    
    cursor.execute('''
        INSERT INTO system_state (key, value, updated_at)
        VALUES ('last_heartbeat', ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    ''', (now, now))
    
    conn.commit()
    conn.close()


def get_last_heartbeat(db_path: str = DEFAULT_DB_PATH) -> Optional[str]:
    """Get the last heartbeat timestamp."""
    try:
        init_system_state_table(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM system_state WHERE key = ?', ('last_heartbeat',))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    except Exception:
        return None


def get_symbol_exposure(symbol: str, db_path: str = DEFAULT_DB_PATH) -> float:
    """Get total exposure for a symbol today."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    cursor.execute('''
        SELECT COALESCE(SUM(amount * buy_price), 0)
        FROM trades
        WHERE symbol = ? AND DATE(timestamp) = ?
    ''', (symbol, today))
    
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else 0.0


# =============================================================================
# PARAMETERS TABLE - Remote configuration from dashboard
# =============================================================================

DEFAULT_PARAMETERS = {
    "MAX_CAPITAL_PER_TRADE_USD": {
        "value": 500.0, "min": 1.0, "max": 10000.0,
        "description": "Maximum capital per single trade in USD"
    },
    "MAX_DAILY_LOSS_USD": {
        "value": 1000.0, "min": 5.0, "max": 50000.0,
        "description": "Maximum daily loss before circuit breaker triggers"
    },
    "MAX_TRADES_PER_HOUR": {
        "value": 50.0, "min": 1.0, "max": 500.0,
        "description": "Maximum number of trades per hour"
    },
    "MAX_SYMBOL_EXPOSURE_USD": {
        "value": 2000.0, "min": 10.0, "max": 100000.0,
        "description": "Maximum exposure per symbol in USD"
    },
    "MAX_BALANCE_USAGE_PER_EXCHANGE": {
        "value": 0.5, "min": 0.05, "max": 0.9,
        "description": "Maximum percentage of exchange balance to use (0.0-1.0)"
    },
    "MIN_SPREAD_PERCENT": {
        "value": 0.3, "min": 0.05, "max": 5.0,
        "description": "Minimum spread percentage for arbitrage"
    },
    "VOLATILITY_THRESHOLD_PERCENT": {
        "value": 2.0, "min": 0.5, "max": 10.0,
        "description": "Maximum volatility percentage for trading"
    },
    "SAFETY_MARGIN_SPREAD": {
        "value": 0.15, "min": 0.05, "max": 5.0,
        "description": "Additional safety margin for spread calculation"
    },
}


def init_parameters(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize the parameters table and populate with defaults if empty."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            value REAL NOT NULL,
            min_value REAL NOT NULL,
            max_value REAL NOT NULL,
            description TEXT,
            updated_at TEXT
        )
    ''')
    
    cursor.execute('SELECT COUNT(*) FROM parameters')
    count = cursor.fetchone()[0]
    
    if count == 0:
        now = datetime.utcnow().isoformat()
        for name, config in DEFAULT_PARAMETERS.items():
            cursor.execute('''
                INSERT INTO parameters (name, value, min_value, max_value, description, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, config["value"], config["min"], config["max"], config["description"], now))
    
    conn.commit()
    conn.close()


def get_all_parameters(db_path: str = DEFAULT_DB_PATH) -> list:
    """Get all parameters from the database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT name, value, min_value, max_value, description, updated_at FROM parameters ORDER BY name')
        rows = cursor.fetchall()
        params = [dict(row) for row in rows]
        
        conn.close()
        return params
    except Exception:
        return []


def get_parameter(name: str, db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    """Get a single parameter by name."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT name, value, min_value, max_value, description, updated_at FROM parameters WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def update_parameter(name: str, new_value: float, db_path: str = DEFAULT_DB_PATH) -> tuple[bool, str]:
    """
    Update a parameter value with validation.
    Returns (success, message) tuple.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT min_value, max_value FROM parameters WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return False, "Unknown parameter"
        
        min_val, max_val = row["min_value"], row["max_value"]
        
        if not (min_val <= new_value <= max_val):
            conn.close()
            return False, f"Value out of allowed range ({min_val} - {max_val})"
        
        now = datetime.utcnow().isoformat()
        cursor.execute('''
            UPDATE parameters SET value = ?, updated_at = ? WHERE name = ?
        ''', (new_value, now, name))
        
        conn.commit()
        conn.close()
        return True, "Parameter updated"
    except Exception as e:
        return False, str(e)
