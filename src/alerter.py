"""
Email alerting module for Price Tracker.

Sends HTML email notifications when a tracked product's price
drops below the user-defined threshold.

Configuration is pulled from environment variables:
    SMTP_HOST       — SMTP server hostname (default: smtp.gmail.com)
    SMTP_PORT       — SMTP server port (default: 587)
    SMTP_USER       — SMTP login username / email
    SMTP_PASSWORD   — SMTP login password (app password for Gmail)
    ALERT_EMAIL_FROM — "From" address (defaults to SMTP_USER)
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.utils import format_currency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _smtp_config() -> dict:
    """Load SMTP settings from environment."""
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("ALERT_EMAIL_FROM", os.environ.get("SMTP_USER", "")),
    }


def _is_configured() -> bool:
    """Check whether SMTP credentials are present."""
    cfg = _smtp_config()
    return bool(cfg["user"] and cfg["password"])


# ---------------------------------------------------------------------------
# Email template
# ---------------------------------------------------------------------------

def _build_email_html(
    product_name: str,
    product_url: str,
    current_price: float,
    threshold: float,
    currency: str = "USD",
) -> str:
    """Render a clean HTML email body."""
    current_fmt = format_currency(current_price, currency)
    threshold_fmt = format_currency(threshold, currency)
    savings_pct = ((threshold - current_price) / threshold) * 100

    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f4f4f7; margin: 0; padding: 0; }}
    .container {{ max-width: 560px; margin: 32px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .header {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; padding: 28px 32px; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
    .header p {{ margin: 8px 0 0; opacity: 0.9; font-size: 14px; }}
    .body {{ padding: 28px 32px; }}
    .price-card {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0; }}
    .price-card .current {{ font-size: 36px; font-weight: 800; color: #16a34a; }}
    .price-card .label {{ font-size: 13px; color: #6b7280; margin-top: 4px; }}
    .details {{ font-size: 14px; color: #374151; line-height: 1.7; }}
    .details strong {{ color: #111827; }}
    .cta {{ display: inline-block; margin-top: 20px; padding: 12px 28px; background: #6366f1; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px; }}
    .cta:hover {{ background: #4f46e5; }}
    .footer {{ padding: 16px 32px; font-size: 12px; color: #9ca3af; text-align: center; border-top: 1px solid #f3f4f6; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🔔 Price Drop Alert!</h1>
      <p>A product you're tracking just dropped in price.</p>
    </div>
    <div class="body">
      <p class="details"><strong>Product:</strong> {product_name}</p>
      <div class="price-card">
        <div class="current">{current_fmt}</div>
        <div class="label">Current Price — {savings_pct:.0f}% below your target of {threshold_fmt}</div>
      </div>
      <p class="details">
        <strong>Your threshold:</strong> {threshold_fmt}<br>
        <strong>Current price:</strong> {current_fmt}
      </p>
      <a class="cta" href="{product_url}" target="_blank">View Product →</a>
    </div>
    <div class="footer">
      You're receiving this because you set up a price alert with Price Tracker.
    </div>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_price_alert(
    product_name: str,
    product_url: str,
    current_price: float,
    threshold: float,
    currency: str = "USD",
    recipient_email: Optional[str] = None,
) -> bool:
    """
    Send a price-drop email alert.

    Parameters
    ----------
    product_name   : Displayed product title.
    product_url    : Direct link to the product page.
    current_price  : The newly detected (lower) price.
    threshold      : The user's target price.
    currency       : ISO currency code for formatting.
    recipient_email: Override recipient (falls back to SMTP_USER).

    Returns True on success, False on failure.
    """
    if not _is_configured():
        logger.error(
            "SMTP is not configured. Set SMTP_USER and SMTP_PASSWORD env vars."
        )
        return False

    cfg = _smtp_config()
    to_addr = recipient_email or cfg["from_addr"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"💰 Price Drop! {product_name} is now {format_currency(current_price, currency)}"
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_addr

    # Plain-text fallback
    plain = (
        f"Price Drop Alert!\n\n"
        f"Product: {product_name}\n"
        f"Current Price: {format_currency(current_price, currency)}\n"
        f"Your Threshold: {format_currency(threshold, currency)}\n"
        f"Link: {product_url}\n"
    )
    msg.attach(MIMEText(plain, "plain"))

    # HTML version
    html = _build_email_html(product_name, product_url, current_price, threshold, currency)
    msg.attach(MIMEText(html, "html"))

    try:
        logger.info("Sending price alert to %s via %s:%s", to_addr, cfg["host"], cfg["port"])
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_addr"], [to_addr], msg.as_string())
        logger.info("Alert email sent successfully.")
        return True
    except Exception as exc:
        logger.error("Failed to send alert email: %s", exc)
        return False
