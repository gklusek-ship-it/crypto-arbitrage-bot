# Crypto Arbitrage Bot

A production-grade cryptocurrency arbitrage bot for cross-exchange trading between **Kraken** and **OKX**.

## Features

- **Cross-exchange arbitrage** - Scans for price discrepancies between Kraken and OKX
- **Risk management** - Circuit breakers, exposure limits, volatility checks
- **Shadow trading** - Risk-free simulation mode for testing strategies
- **Real-time dashboard** - Web interface with live stats and charts
- **Remote parameter editing** - Adjust bot parameters from the dashboard
- **Alerts** - Telegram and email notifications
- **DRY_RUN mode** - Safe testing without real orders

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure API keys in `.env`:
```
KRAKEN_API_KEY=your_key
KRAKEN_API_SECRET=your_secret
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
```

3. Run the bot:
```bash
python main.py
```

4. Run the dashboard (optional):
```bash
python api.py
```

## Configuration

Edit `config.py` to adjust:
- Trading pairs
- Risk limits
- Minimum spread threshold
- Exchange fees

## Dashboard

Access at `http://localhost:5000` when running `api.py`:
- Live trading statistics
- Daily PnL chart
- Exchange fees display
- Shadow trading performance
- Remote parameter editing

## License

MIT
