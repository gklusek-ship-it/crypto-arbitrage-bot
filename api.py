"""
Flask API backend for the Arbitrage Bot Dashboard.

=== HOW TO RUN ===

On Replit:
1. Run the bot: python main.py (in one terminal)
2. Run the dashboard: python api.py (automatically starts on port 5000)
3. Open the webview to see the dashboard

On VPS:
1. Install dependencies: pip install flask ccxt python-dotenv
2. Run: python main.py & python api.py
3. Access at http://your-server-ip:5000
4. Optional: Use nginx as reverse proxy for production
"""

import os
from flask import Flask, jsonify, render_template, request
from db import (
    init_db, get_recent_trades, get_pnl_summary, get_overall_stats, get_last_heartbeat,
    init_parameters, get_all_parameters, get_parameter, update_parameter
)
from shadow import get_shadow_trades, get_shadow_stats
from risk import get_trading_enabled, get_api_error_count, get_trades_this_hour, get_last_alert_message
from optimizer import compare_shadow_vs_real
from param_store import get_store
from logger import get_logger
import config

logger = get_logger(__name__)

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

init_db()
init_parameters()


@app.route("/")
def index():
    """Serve the dashboard HTML page."""
    return render_template("dashboard.html")


@app.route("/api/trades/recent")
def api_recent_trades():
    """Get the most recent trades."""
    trades = get_recent_trades(limit=100)
    return jsonify(trades)


@app.route("/api/stats/summary")
def api_stats_summary():
    """Get overall trading statistics."""
    stats = get_overall_stats()
    return jsonify(stats)


@app.route("/api/stats/daily_pnl")
def api_daily_pnl():
    """Get daily PNL for the last 14 days."""
    summary = get_pnl_summary(days=14)
    return jsonify(summary)


@app.route("/api/health")
def api_health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/api/fees")
def api_fees():
    """Get exchange fees configuration."""
    fees = []
    for exchange_id, fee_data in config.EXCHANGE_FEES.items():
        if exchange_id in config.SUPPORTED_EXCHANGES:
            fees.append({
                "exchange": exchange_id,
                "maker": fee_data["maker"] * 100,
                "taker": fee_data["taker"] * 100
            })
    return jsonify(fees)


@app.route("/api/diagnostics")
def api_diagnostics():
    """
    Comprehensive diagnostics endpoint.
    Returns system status, trading metrics, and alerts.
    """
    real_stats = get_overall_stats()
    shadow_stats = get_shadow_stats(days=7)
    
    diagnostics = {
        "last_heartbeat": get_last_heartbeat(),
        "trading_enabled": get_trading_enabled(),
        "daily_pnl_usd": real_stats.get("total_pnl_usd", 0),
        "api_error_count": get_api_error_count(),
        "trades_this_hour": get_trades_this_hour(),
        "max_trades_per_hour": config.MAX_TRADES_PER_HOUR,
        "last_alert_message": get_last_alert_message(),
        "dry_run_mode": config.DRY_RUN,
        "real_trading": {
            "total_trades": real_stats.get("total_trades", 0),
            "total_pnl_usd": real_stats.get("total_pnl_usd", 0),
            "win_rate": real_stats.get("win_rate", 0),
            "avg_pnl_per_trade": real_stats.get("avg_pnl_per_trade", 0),
            "best_trade_pnl": real_stats.get("best_trade_pnl", 0),
            "worst_trade_pnl": real_stats.get("worst_trade_pnl", 0)
        },
        "shadow_trading": {
            "total_trades": shadow_stats.get("total_trades", 0),
            "total_pnl_usd": shadow_stats.get("total_pnl_usd", 0),
            "win_rate": shadow_stats.get("win_rate", 0),
            "avg_pnl_per_trade": shadow_stats.get("avg_pnl_per_trade", 0)
        },
        "config": {
            "exchanges": config.SUPPORTED_EXCHANGES,
            "trading_pairs": config.TRADING_PAIRS,
            "min_spread_percent": config.MIN_SPREAD_PERCENT,
            "max_capital_per_trade_usd": config.MAX_CAPITAL_PER_TRADE_USD,
            "max_daily_loss_usd": config.MAX_DAILY_LOSS_USD,
            "volatility_threshold": config.VOLATILITY_THRESHOLD_PERCENT,
            "safety_margin_spread": config.SAFETY_MARGIN_SPREAD
        },
        "live_params": get_store().get_all(),
        "params_last_reload": get_store().get_last_reload_time()
    }
    
    return jsonify(diagnostics)


@app.route("/api/shadow/trades")
def api_shadow_trades():
    """Get recent shadow trades."""
    trades = get_shadow_trades(limit=100)
    return jsonify(trades)


@app.route("/api/shadow/stats")
def api_shadow_stats():
    """Get shadow trading statistics."""
    stats = get_shadow_stats(days=14)
    return jsonify(stats)


@app.route("/api/compare")
def api_compare():
    """Compare real vs shadow trading performance."""
    comparison = compare_shadow_vs_real(days=7)
    return jsonify(comparison)


# =============================================================================
# PARAMETER ENDPOINTS - Remote configuration from dashboard
# =============================================================================
# To add a new parameter:
# 1. Add it to DEFAULT_PARAMETERS in db.py with value, min, max, description
# 2. Delete trades.db or run SQL to insert the new row
# 3. The parameter will appear in the dashboard automatically


@app.route("/api/params")
def api_get_params():
    """
    Get all configurable parameters.
    Returns list of parameters with name, value, min/max range, and description.
    """
    params = get_all_parameters()
    return jsonify(params)


@app.route("/api/params/update", methods=["POST"])
def api_update_param():
    """
    Update a single parameter.
    Expects JSON: { "name": "PARAM_NAME", "value": 123.45 }
    Validates against min/max range before saving.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Invalid JSON"}), 400
        
        name = data.get("name")
        value = data.get("value")
        
        if not name or value is None:
            return jsonify({"success": False, "message": "Missing name or value"}), 400
        
        try:
            new_value = float(value)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Value must be a number"}), 400
        
        param = get_parameter(name)
        if not param:
            return jsonify({"success": False, "message": "Unknown parameter"}), 404
        
        success, message = update_parameter(name, new_value)
        
        if success:
            logger.info(f"Parameter updated: {name} = {new_value} (was {param['value']})")
            store = get_store()
            store.reload_params()
        
        return jsonify({"success": success, "message": message})
    
    except Exception as e:
        logger.error(f"Error updating parameter: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
