"""
Utility functions for the arbitrage bot.

Example .env file structure:
----------------------------
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here
KRAKEN_API_KEY=your_kraken_api_key_here
KRAKEN_API_SECRET=your_kraken_api_secret_here
BYBIT_API_KEY=your_bybit_api_key_here
BYBIT_API_SECRET=your_bybit_api_secret_here
OKX_API_KEY=your_okx_api_key_here
OKX_API_SECRET=your_okx_api_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password_here
ALERT_EMAIL=recipient@example.com
----------------------------
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dotenv import load_dotenv

from logger import get_logger

logger = get_logger(__name__)


def load_env() -> None:
    """Load environment variables from .env file."""
    load_dotenv()


def format_opportunity(opportunity: dict) -> str:
    """Format an arbitrage opportunity for logging."""
    return (
        f"[{opportunity['symbol']}] "
        f"BUY on {opportunity['buy_exchange_id']} @ {opportunity['buy_price']:.2f} | "
        f"SELL on {opportunity['sell_exchange_id']} @ {opportunity['sell_price']:.2f} | "
        f"Raw spread: {opportunity['raw_spread_percent']:.3f}% | "
        f"Net spread: {opportunity['net_spread_percent']:.3f}%"
    )


def usd_to_coin_amount(usd_amount: float, coin_price: float) -> float:
    """Convert USD amount to coin quantity based on price."""
    if coin_price <= 0:
        return 0.0
    return usd_amount / coin_price


def extract_base_quote(symbol: str) -> tuple[str, str]:
    """Extract base and quote currencies from a trading pair symbol."""
    parts = symbol.split("/")
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def send_telegram(message: str) -> bool:
    """
    Send a message via Telegram bot.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment.
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests library not installed, cannot send Telegram message")
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.debug("Telegram credentials not configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.debug("Telegram message sent successfully")
            return True
        else:
            logger.warning(f"Telegram API error: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def send_email(message: str, subject: str = "Arbitrage Bot Alert") -> bool:
    """
    Send an email alert.
    Requires SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL in environment.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    alert_email = os.getenv("ALERT_EMAIL")

    if not all([smtp_host, smtp_user, smtp_password, alert_email]):
        logger.debug("Email credentials not configured")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = str(smtp_user)
        msg["To"] = str(alert_email)
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        server = smtplib.SMTP(str(smtp_host), int(smtp_port))
        server.starttls()
        server.login(str(smtp_user), str(smtp_password))
        server.send_message(msg)
        server.quit()

        logger.debug("Email alert sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def send_alert(message: str, subject: str = "Arbitrage Bot Alert") -> None:
    """Send alert via all configured channels (Telegram, Email)."""
    logger.info(f"ALERT: {message}")
    send_telegram(f"🤖 <b>{subject}</b>\n\n{message}")
    send_email(message, subject)


def format_usd(value: float) -> str:
    """Format a value as USD currency."""
    if value >= 0:
        return f"${value:.2f}"
    return f"-${abs(value):.2f}"


def format_percent(value: float) -> str:
    """Format a value as percentage."""
    return f"{value:.2f}%"
