"""
Utility functions for URL validation, price parsing, and formatting.
"""

import re
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# URL Helpers
# ---------------------------------------------------------------------------

def sanitize_url(url: str) -> str:
    """
    Validate and sanitize a product page URL.

    - Strips whitespace
    - Ensures the scheme is http or https
    - Rejects obviously invalid URLs

    Returns the cleaned URL string.
    Raises ValueError on invalid input.
    """
    url = url.strip()

    if not url:
        raise ValueError("URL cannot be empty.")

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError(f"Invalid URL domain: {parsed.netloc}")

    # Basic injection guard — reject URLs with suspicious characters
    if any(ch in url for ch in [";", "'", '"', "<", ">", "{", "}"]):
        raise ValueError("URL contains potentially unsafe characters.")

    return url


# ---------------------------------------------------------------------------
# Price Parsing
# ---------------------------------------------------------------------------

# Regex: optional currency symbol/code, then digits with possible separators
_PRICE_PATTERN = re.compile(
    r"(?:[\$€£₹¥₩]|USD|EUR|GBP|INR|JPY|KRW)?\s*"
    r"([\d]{1,3}(?:[,.\s]?\d{3})*(?:[.,]\d{1,2})?)"
)

# Currency symbols we recognise
_CURRENCY_SYMBOLS = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR",
    "¥": "JPY", "₩": "KRW",
}


def parse_price(text: str) -> float | None:
    """
    Extract a numeric price from a string that may contain currency symbols,
    thousand separators, and varied decimal conventions.

    Examples:
        "$1,299.99"   → 1299.99
        "€ 19,99"     → 19.99
        "₹1,49,999"   → 149999.0
        "1.299,00 €"  → 1299.0

    Returns None if no price can be parsed.
    """
    if not text:
        return None

    text = text.strip()

    # Remove currency codes / symbols for cleaner matching
    cleaned = text
    for sym in list(_CURRENCY_SYMBOLS.keys()) + list(_CURRENCY_SYMBOLS.values()):
        cleaned = cleaned.replace(sym, "")
    cleaned = cleaned.strip()

    if not cleaned:
        return None

    # Determine decimal separator heuristic:
    # If the last separator is a comma with ≤2 digits after → European style
    # If the last separator is a dot   with ≤2 digits after → US/UK style
    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")

    if last_comma > last_dot and len(cleaned) - last_comma - 1 <= 2:
        # European: comma is decimal, dots are thousand separators
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # US/UK: dot is decimal (or no decimal), commas are thousand separators
        cleaned = cleaned.replace(",", "")

    # Remove any remaining whitespace / non-numeric except dot
    cleaned = re.sub(r"[^\d.]", "", cleaned)

    try:
        return float(cleaned)
    except ValueError:
        return None


def detect_currency(text: str) -> str:
    """
    Attempt to detect the currency from a price string.
    Falls back to "USD" if nothing recognised.
    """
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code

    upper = text.upper()
    for code in _CURRENCY_SYMBOLS.values():
        if code in upper:
            return code

    return "USD"


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format a numeric amount with currency symbol for display."""
    symbols = {v: k for k, v in _CURRENCY_SYMBOLS.items()}
    sym = symbols.get(currency, "$")
    return f"{sym}{amount:,.2f}"
