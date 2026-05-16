"""
Price Tracker — Flask API Server.

Serves both the REST API and the static frontend.
Run with: python server.py
"""

import logging
import os
import sys
import threading

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
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
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("price_tracker.server")

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

init_db()


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.route("/")
def serve_index():
    return send_from_directory("static", "index.html")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@app.route("/api/products", methods=["GET"])
def api_list_products():
    """List all tracked products."""
    products = list_products()
    return jsonify({"products": products})


@app.route("/api/products", methods=["POST"])
def api_add_product():
    """Add a new product to track."""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    threshold = data.get("threshold")
    email = data.get("email", "").strip() or None

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if threshold is None:
        return jsonify({"error": "Threshold price is required."}), 400

    try:
        threshold = float(threshold)
        if threshold <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Threshold must be a positive number."}), 400

    try:
        url = sanitize_url(url)
    except ValueError as e:
        return jsonify({"error": f"Invalid URL: {e}"}), 400

    # Scrape in a try block
    try:
        result = scrape_product(url)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch product page: {e}"}), 502

    name = result.name or "Unknown Product"
    currency = result.currency

    try:
        product_id = add_product(
            url=url,
            threshold=threshold,
            currency=currency,
            name=name,
            alert_email=email,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": "This URL is already being tracked."}), 409
        return jsonify({"error": str(e)}), 500

    # Record initial price
    if result.price is not None:
        add_price_record(product_id, result.price)
        update_product(product_id, last_price=result.price, name=name)

    product = get_product(product_id)

    # Check if already at/below threshold
    alert_triggered = False
    if result.price is not None and result.price <= threshold:
        alert_triggered = True
        _trigger_alert_async(product_id, result.price)

    return jsonify({
        "product": product,
        "scraped_price": result.price,
        "alert_triggered": alert_triggered,
    }), 201


@app.route("/api/products/<int:product_id>", methods=["GET"])
def api_get_product(product_id):
    """Get a single product."""
    product = get_product(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404
    return jsonify({"product": product})


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def api_remove_product(product_id):
    """Remove a tracked product."""
    product = get_product(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    remove_product(product_id)
    return jsonify({"message": f"Product '{product.get('name', 'Unknown')}' removed."})


@app.route("/api/products/<int:product_id>/history", methods=["GET"])
def api_get_history(product_id):
    """Get price history for a product."""
    product = get_product(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    limit = request.args.get("limit", 50, type=int)
    history = get_price_history(product_id, limit=limit)
    return jsonify({"product": product, "history": history})


@app.route("/api/products/<int:product_id>/check", methods=["POST"])
def api_check_product(product_id):
    """Run a price check for a single product."""
    product = get_product(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    try:
        result = scrape_product(product["url"])
    except Exception as e:
        return jsonify({"error": f"Scraping failed: {e}"}), 502

    if result.price is None:
        return jsonify({
            "product": product,
            "error": "Could not extract price from the page.",
            "price": None,
        }), 200

    # Record price
    add_price_record(product_id, result.price)
    updates = {"last_price": result.price}
    if result.name:
        updates["name"] = result.name
    update_product(product_id, **updates)

    # Refresh product data
    product = get_product(product_id)
    threshold = product["threshold"]

    alert_triggered = False
    if result.price <= threshold:
        alert_triggered = True
        _trigger_alert_async(product_id, result.price)

    return jsonify({
        "product": product,
        "price": result.price,
        "alert_triggered": alert_triggered,
    })


@app.route("/api/products/check-all", methods=["POST"])
def api_check_all():
    """Run price checks for all tracked products."""
    products = list_products()
    results = []

    for prod in products:
        pid = prod["id"]
        try:
            result = scrape_product(prod["url"])
            if result.price is not None:
                add_price_record(pid, result.price)
                updates = {"last_price": result.price}
                if result.name:
                    updates["name"] = result.name
                update_product(pid, **updates)

                alert_triggered = False
                if result.price <= prod["threshold"]:
                    alert_triggered = True
                    _trigger_alert_async(pid, result.price)

                results.append({
                    "product_id": pid,
                    "name": result.name or prod.get("name"),
                    "price": result.price,
                    "threshold": prod["threshold"],
                    "alert_triggered": alert_triggered,
                    "status": "success",
                })
            else:
                results.append({
                    "product_id": pid,
                    "name": prod.get("name"),
                    "status": "error",
                    "error": "Could not extract price.",
                })
        except Exception as e:
            results.append({
                "product_id": pid,
                "name": prod.get("name"),
                "status": "error",
                "error": str(e),
            })

    return jsonify({"results": results})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trigger_alert_async(product_id: int, current_price: float):
    """Send alert in a background thread so the API doesn't block."""
    def _send():
        product = get_product(product_id)
        if not product:
            return
        send_price_alert(
            product_name=product.get("name", "Unknown"),
            product_url=product["url"],
            current_price=current_price,
            threshold=product["threshold"],
            currency=product.get("currency", "USD"),
            recipient_email=product.get("alert_email"),
        )
    threading.Thread(target=_send, daemon=True).start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  🏷️  Price Tracker running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)
