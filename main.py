#!/usr/bin/env python3
"""
Price Tracker — CLI entry point.

Commands
--------
  add       Add a product URL to track with a price threshold.
  check     Run a price check for one or all tracked products.
  list      List all tracked products.
  history   Show price history for a tracked product.
  remove    Remove a tracked product.

Usage
-----
  python main.py add "https://example.com/product" 29.99
  python main.py check
  python main.py check --id 1
  python main.py list
  python main.py history 1
  python main.py remove 1
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.database import (
    init_db,
    add_product,
    get_product,
    list_products,
    update_product,
    remove_product,
    add_price_record,
    get_price_history,
)
from src.scraper import scrape_product
from src.alerter import send_price_alert
from src.utils import sanitize_url, format_currency

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("price_tracker")


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> None:
    """Add a new product to track."""
    try:
        url = sanitize_url(args.url)
    except ValueError as e:
        print(f"❌ Invalid URL: {e}")
        sys.exit(1)

    if args.threshold <= 0:
        print("❌ Threshold must be a positive number.")
        sys.exit(1)

    print(f"🔍 Fetching product page: {url}")
    try:
        result = scrape_product(url)
    except Exception as e:
        print(f"❌ Failed to fetch product page: {e}")
        sys.exit(1)

    if result.price is None:
        print("⚠️  Could not extract a price from the page.")
        print("   The product will be added, but verify the URL is correct.")

    name = result.name or "Unknown Product"
    currency = result.currency

    try:
        product_id = add_product(
            url=url,
            threshold=args.threshold,
            currency=currency,
            name=name,
            alert_email=args.email,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            print("⚠️  This URL is already being tracked.")
            sys.exit(1)
        raise

    # Record initial price
    if result.price is not None:
        add_price_record(product_id, result.price)
        update_product(product_id, last_price=result.price, name=name)

    print()
    print("✅ Product added successfully!")
    print(f"   ID:        {product_id}")
    print(f"   Name:      {name}")
    print(f"   Price:     {format_currency(result.price, currency) if result.price else 'N/A'}")
    print(f"   Threshold: {format_currency(args.threshold, currency)}")
    print(f"   Currency:  {currency}")
    if args.email:
        print(f"   Alert to:  {args.email}")

    # Immediate threshold check
    if result.price is not None and result.price <= args.threshold:
        print()
        print(f"🎉 The current price is already at or below your threshold!")
        _trigger_alert(product_id, result.price)


def cmd_check(args: argparse.Namespace) -> None:
    """Run price checks for tracked products."""
    init_db()

    if args.id:
        product = get_product(args.id)
        if not product:
            print(f"❌ No product found with ID {args.id}")
            sys.exit(1)
        products = [product]
    else:
        products = list_products()

    if not products:
        print("📭 No products are being tracked. Use 'add' to start tracking.")
        return

    print(f"🔄 Checking {len(products)} product(s)...\n")
    alerts_sent = 0

    for prod in products:
        product_id = prod["id"]
        url = prod["url"]
        threshold = prod["threshold"]
        currency = prod.get("currency", "USD")
        old_name = prod.get("name", "Unknown")

        print(f"  [{product_id}] {old_name}")
        print(f"      URL: {url}")

        try:
            result = scrape_product(url)
        except Exception as e:
            print(f"      ❌ Scraping failed: {e}")
            print()
            continue

        if result.price is None:
            print(f"      ⚠️  Could not extract price.")
            print()
            continue

        # Update stored data
        add_price_record(product_id, result.price)
        updates = {"last_price": result.price}
        if result.name:
            updates["name"] = result.name
        update_product(product_id, **updates)

        previous = prod.get("last_price")
        price_change = ""
        if previous is not None:
            diff = result.price - previous
            if diff < 0:
                price_change = f" (↓ {format_currency(abs(diff), currency)})"
            elif diff > 0:
                price_change = f" (↑ {format_currency(diff, currency)})"
            else:
                price_change = " (no change)"

        print(f"      Price: {format_currency(result.price, currency)}{price_change}")
        print(f"      Threshold: {format_currency(threshold, currency)}")

        if result.price <= threshold:
            print(f"      🎉 PRICE DROP DETECTED!")
            if _trigger_alert(product_id, result.price):
                alerts_sent += 1
        else:
            gap = result.price - threshold
            print(f"      📊 {format_currency(gap, currency)} above threshold")

        print()

    print(f"✅ Check complete. {alerts_sent} alert(s) sent.")


def cmd_list(args: argparse.Namespace) -> None:
    """Display all tracked products."""
    init_db()
    products = list_products()

    if not products:
        print("📭 No products being tracked. Use 'add' to start.")
        return

    print(f"📋 Tracked Products ({len(products)})\n")
    print(f"{'ID':<5} {'Name':<40} {'Last Price':<14} {'Threshold':<14} {'Currency'}")
    print("─" * 90)

    for p in products:
        pid = p["id"]
        name = (p.get("name") or "Unknown")[:38]
        currency = p.get("currency", "USD")
        last_price = format_currency(p["last_price"], currency) if p.get("last_price") else "N/A"
        threshold = format_currency(p["threshold"], currency)
        print(f"{pid:<5} {name:<40} {last_price:<14} {threshold:<14} {currency}")

    print()


def cmd_history(args: argparse.Namespace) -> None:
    """Show price history for a product."""
    init_db()
    product = get_product(args.id)

    if not product:
        print(f"❌ No product found with ID {args.id}")
        sys.exit(1)

    history = get_price_history(args.id, limit=args.limit)

    print(f"📈 Price History — {product.get('name', 'Unknown')}")
    print(f"   URL: {product['url']}")
    print(f"   Threshold: {format_currency(product['threshold'], product.get('currency', 'USD'))}")
    print()

    if not history:
        print("   No price records yet.")
        return

    currency = product.get("currency", "USD")
    print(f"   {'Date':<24} {'Price':<14} {'vs Threshold'}")
    print("   " + "─" * 55)

    for record in history:
        date = record["checked_at"][:19].replace("T", " ")
        price = format_currency(record["price"], currency)
        diff = record["price"] - product["threshold"]
        if diff <= 0:
            status = f"✅ {format_currency(abs(diff), currency)} below"
        else:
            status = f"   {format_currency(diff, currency)} above"
        print(f"   {date:<24} {price:<14} {status}")

    print()


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove a tracked product."""
    init_db()
    product = get_product(args.id)

    if not product:
        print(f"❌ No product found with ID {args.id}")
        sys.exit(1)

    name = product.get("name", "Unknown")

    if not args.force:
        confirm = input(f"Remove '{name}' (ID {args.id})? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    removed = remove_product(args.id)
    if removed:
        print(f"🗑️  Removed: {name}")
    else:
        print("❌ Failed to remove product.")


# ---------------------------------------------------------------------------
# Alert helper
# ---------------------------------------------------------------------------

def _trigger_alert(product_id: int, current_price: float) -> bool:
    """Send a price-drop alert for the given product. Returns True on success."""
    product = get_product(product_id)
    if not product:
        return False

    name = product.get("name", "Unknown Product")
    url = product["url"]
    threshold = product["threshold"]
    currency = product.get("currency", "USD")
    recipient = product.get("alert_email")

    success = send_price_alert(
        product_name=name,
        product_url=url,
        current_price=current_price,
        threshold=threshold,
        currency=currency,
        recipient_email=recipient,
    )

    if success:
        print(f"      📧 Alert email sent!")
    else:
        print(f"      ⚠️  Could not send alert email (check SMTP configuration)")

    return success


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="price-tracker",
        description="🏷️  Price Tracker — Monitor product prices and get alerted on drops.",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- add ---
    p_add = sub.add_parser("add", help="Add a product to track")
    p_add.add_argument("url", type=str, help="Product page URL")
    p_add.add_argument("threshold", type=float, help="Target price threshold")
    p_add.add_argument("--email", type=str, default=None, help="Override alert email recipient")
    p_add.set_defaults(func=cmd_add)

    # --- check ---
    p_check = sub.add_parser("check", help="Run price check(s)")
    p_check.add_argument("--id", type=int, default=None, help="Check a specific product ID")
    p_check.set_defaults(func=cmd_check)

    # --- list ---
    p_list = sub.add_parser("list", help="List all tracked products")
    p_list.set_defaults(func=cmd_list)

    # --- history ---
    p_hist = sub.add_parser("history", help="Show price history")
    p_hist.add_argument("id", type=int, help="Product ID")
    p_hist.add_argument("--limit", type=int, default=20, help="Max records to show")
    p_hist.set_defaults(func=cmd_history)

    # --- remove ---
    p_rm = sub.add_parser("remove", help="Remove a tracked product")
    p_rm.add_argument("id", type=int, help="Product ID to remove")
    p_rm.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    p_rm.set_defaults(func=cmd_remove)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Ensure DB is ready
    init_db()

    # Load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    args.func(args)


if __name__ == "__main__":
    main()
