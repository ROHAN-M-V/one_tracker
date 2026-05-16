"""
Web scraper for extracting product names and prices from e-commerce pages.

Employs a multi-strategy approach:
  1. Schema.org JSON-LD structured data
  2. Open Graph / meta tags
  3. Common CSS selector patterns
  4. Regex fallback on visible text

Two fetching modes:
  - Fast mode: requests + BeautifulSoup (for static HTML)
  - Browser mode: Playwright headless Chromium (for JS-rendered pages like Amazon)

If the fast mode fails to find a price, the scraper automatically retries
with the browser mode.
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.utils import parse_price, detect_currency

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

_REQUEST_TIMEOUT = 15  # seconds

_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds (base; exponential back-off applied)

# Domains known to require JavaScript rendering
_JS_REQUIRED_DOMAINS = {
    "amazon.com", "amazon.in", "amazon.co.uk", "amazon.de", "amazon.fr",
    "amazon.ca", "amazon.co.jp", "amazon.com.au",
    "flipkart.com",
    "walmart.com",
    "bestbuy.com",
    "target.com",
    "ebay.com",
}

# CSS selectors commonly used for prices on popular e-commerce sites
_PRICE_SELECTORS = [
    # Amazon
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    ".a-price .a-offscreen",
    "span.a-price-whole",
    "#corePrice_feature_div .a-offscreen",
    "#tp_price_block_total_price_ww .a-offscreen",
    ".priceToPay .a-offscreen",
    "#apex_offerDisplay_desktop .a-offscreen",
    # Generic / common patterns
    "[data-price]",
    "[itemprop='price']",
    ".price-current",
    ".product-price",
    ".sale-price",
    ".current-price",
    ".price",
    ".price__current",
    "#price",
    ".price-tag",
    ".product__price",
    # Flipkart
    "div._30jeq3",
    "div._16Jk6d",
    # Best Buy
    ".priceView-customer-price span",
    # Walmart
    "[data-testid='price-wrap'] .f2",
    "span[itemprop='price']",
]

_NAME_SELECTORS = [
    "#productTitle",            # Amazon
    "h1.product-title",
    "h1[itemprop='name']",
    ".product-name h1",
    ".product__title",
    "h1",
]


@dataclass
class ScrapedProduct:
    """Result of scraping a product page."""
    name: Optional[str]
    price: Optional[float]
    currency: str
    url: str
    raw_price_text: Optional[str] = None


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _get_domain(url: str) -> str:
    """Extract the base domain from a URL (e.g., 'amazon.com')."""
    hostname = urlparse(url).hostname or ""
    # Strip 'www.' prefix
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def _needs_browser(url: str) -> bool:
    """Check if this URL is known to require a headless browser."""
    domain = _get_domain(url)
    return any(domain.endswith(d) for d in _JS_REQUIRED_DOMAINS)


def _clean_amazon_url(url: str) -> str:
    """Strip tracking parameters from Amazon URLs, keeping just /dp/ASIN."""
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    if match:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.hostname}/dp/{match.group(1)}"
    return url


# ---------------------------------------------------------------------------
# HTTP layer — requests (fast mode)
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    """Return randomised request headers."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "DNT": "1",
    }


def fetch_page(url: str) -> str:
    """
    Fetch the HTML content of a URL with retries and back-off.

    Returns the page HTML as a string.
    Raises requests.RequestException on persistent failure.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            logger.info("Fetching %s (attempt %d/%d)", url, attempt, _MAX_RETRIES)
            resp = requests.get(
                url,
                headers=_get_headers(),
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < _MAX_RETRIES:
                delay = _RETRY_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)

    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HTTP layer — Playwright (browser mode)
# ---------------------------------------------------------------------------

def _fetch_page_browser(url: str) -> str:
    """
    Fetch a page using a headless Chromium browser via Playwright.
    This handles JavaScript-rendered content (Amazon, Flipkart, etc.).

    Returns the fully rendered page HTML.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
        )
        raise RuntimeError("Playwright is required for this site but is not installed.")

    logger.info("Launching headless browser for: %s", url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        # Block images, fonts, and media to speed up loading
        context.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,mp4,webm}", 
                       lambda route: route.abort())

        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for price elements to appear (common selectors)
            try:
                page.wait_for_selector(
                    ".a-price, .price, [itemprop='price'], #priceblock_ourprice, .priceToPay",
                    timeout=8000,
                )
            except Exception:
                # If no known price selector found, just wait a bit for JS
                page.wait_for_timeout(3000)

            html = page.content()
        finally:
            browser.close()

    logger.info("Browser fetched %d bytes from %s", len(html), url)
    return html


# ---------------------------------------------------------------------------
# Extraction strategies
# ---------------------------------------------------------------------------

def _extract_jsonld(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """
    Look for Schema.org JSON-LD with @type Product.
    Returns (price_text, name) or (None, None).
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both single objects and arrays
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue

            # Might be nested under @graph
            if "@graph" in item:
                items.extend(item["@graph"])
                continue

            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                item_type = " ".join(item_type)

            if "Product" not in item_type:
                continue

            name = item.get("name")

            # Price can be in offers → price, or offers → lowPrice
            offers = item.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = (
                offers.get("price")
                or offers.get("lowPrice")
                or item.get("price")
            )
            if price is not None:
                return str(price), name

    return None, None


def _extract_meta(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """
    Look for Open Graph or generic meta tags for price / product name.
    """
    price_text = None
    name = None

    # Price meta tags
    for attr in ("product:price:amount", "og:price:amount", "twitter:data1"):
        tag = soup.find("meta", property=attr) or soup.find("meta", attrs={"name": attr})
        if tag and tag.get("content"):
            price_text = tag["content"]
            break

    # Name meta tags
    for attr in ("og:title", "twitter:title"):
        tag = soup.find("meta", property=attr) or soup.find("meta", attrs={"name": attr})
        if tag and tag.get("content"):
            name = tag["content"]
            break

    return price_text, name


def _extract_css(soup: BeautifulSoup) -> Optional[str]:
    """
    Try common CSS selectors to find a price element.
    Returns raw price text or None.
    """
    for selector in _PRICE_SELECTORS:
        try:
            el = soup.select_one(selector)
        except Exception:
            continue
        if el:
            # Some elements carry price in a data attribute
            if el.has_attr("data-price"):
                return el["data-price"]
            if el.has_attr("content"):
                return el["content"]
            text = el.get_text(strip=True)
            if text and any(ch.isdigit() for ch in text):
                return text
    return None


def _extract_name_css(soup: BeautifulSoup) -> Optional[str]:
    """Try common selectors for the product name."""
    for selector in _NAME_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            if text and len(text) < 300:
                return text
    return None


def _extract_regex(html: str) -> Optional[str]:
    """
    Last-resort regex scan of the HTML for something that looks like a price.
    Targets patterns like $12.99, €19,99, ₹1,499, etc.
    """
    pattern = re.compile(
        r"[\$€£₹¥₩]\s?\d[\d,.\s]{0,15}\d"
    )
    matches = pattern.findall(html)
    if matches:
        # Return the first plausible match
        return matches[0].strip()
    return None


# ---------------------------------------------------------------------------
# Core extraction pipeline
# ---------------------------------------------------------------------------

def _extract_from_html(html: str, url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Run all extraction strategies on an HTML string.
    Returns (price_text, name, strategy_used) or (None, None, None).
    """
    soup = BeautifulSoup(html, "lxml")
    price_text: Optional[str] = None
    name: Optional[str] = None

    # Strategy 1: JSON-LD
    jld_price, jld_name = _extract_jsonld(soup)
    if jld_price is not None:
        price_text = jld_price
        logger.info("Price found via JSON-LD: %s", price_text)
    if jld_name:
        name = jld_name

    # Strategy 2: Meta tags
    if price_text is None:
        meta_price, meta_name = _extract_meta(soup)
        if meta_price is not None:
            price_text = meta_price
            logger.info("Price found via meta tags: %s", price_text)
        if not name and meta_name:
            name = meta_name

    # Strategy 3: CSS selectors
    if price_text is None:
        css_price = _extract_css(soup)
        if css_price is not None:
            price_text = css_price
            logger.info("Price found via CSS selector: %s", price_text)

    # Strategy 4: Regex fallback
    if price_text is None:
        regex_price = _extract_regex(html)
        if regex_price is not None:
            price_text = regex_price
            logger.info("Price found via regex fallback: %s", price_text)

    # Name fallback
    if not name:
        name = _extract_name_css(soup)
    if not name:
        title_tag = soup.find("title")
        if title_tag:
            name = title_tag.get_text(strip=True)

    return price_text, name, "found" if price_text else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_product(url: str) -> ScrapedProduct:
    """
    Scrape a product page and extract name + price.

    Uses a cascading strategy:
      1. Try fast mode (requests) first
      2. If price not found AND site is JS-heavy, retry with Playwright browser
      3. Extract using: JSON-LD → meta tags → CSS selectors → regex
    """
    # Clean Amazon URLs to avoid tracking-param issues
    original_url = url
    if "amazon." in url:
        url = _clean_amazon_url(url)

    use_browser = _needs_browser(url)

    # ── Attempt 1: Fast mode (requests) ──
    price_text = None
    name = None

    if not use_browser:
        # Only try requests for non-JS sites
        try:
            html = fetch_page(url)
            price_text, name, _ = _extract_from_html(html, url)
        except Exception as e:
            logger.warning("Fast fetch failed: %s", e)

    # ── Attempt 2: Browser mode (Playwright) ──
    if price_text is None:
        logger.info("Trying headless browser for %s", url)
        try:
            html = _fetch_page_browser(url)
            price_text, name_browser, _ = _extract_from_html(html, url)
            if not name and name_browser:
                name = name_browser
        except Exception as e:
            logger.error("Browser fetch failed: %s", e)
            # If browser also fails and we haven't tried requests yet, try it
            if use_browser and price_text is None:
                try:
                    html = fetch_page(url)
                    price_text, name_fallback, _ = _extract_from_html(html, url)
                    if not name and name_fallback:
                        name = name_fallback
                except Exception:
                    pass

    # Parse numeric price
    price = parse_price(price_text) if price_text else None
    currency = detect_currency(price_text or "") if price_text else "USD"

    if price is None:
        logger.warning("Could not extract a numeric price from: %s", url)

    return ScrapedProduct(
        name=name,
        price=price,
        currency=currency,
        url=original_url,
        raw_price_text=price_text,
    )
