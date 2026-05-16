"""
SQLite database layer for the Price Tracker.

Tables
------
products       — tracked product URLs, thresholds, and metadata.
price_history  — timestamped price records linked to products.
"""

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Default DB file lives next to the project root
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "price_tracker.db"


def _get_db_path() -> str:
    """Return the database file path, respecting an env-var override."""
    return os.environ.get("PRICE_TRACKER_DB", str(_DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection."""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row          # dict-like access
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't already exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT    NOT NULL UNIQUE,
                name        TEXT,
                threshold   REAL    NOT NULL,
                currency    TEXT    DEFAULT 'USD',
                last_price  REAL,
                alert_email TEXT,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL,
                price       REAL    NOT NULL,
                checked_at  TEXT    NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_ph_product
                ON price_history(product_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------

def add_product(
    url: str,
    threshold: float,
    currency: str = "USD",
    name: Optional[str] = None,
    alert_email: Optional[str] = None,
) -> int:
    """
    Insert a new tracked product. Returns the new product ID.
    Raises sqlite3.IntegrityError if the URL is already tracked.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO products (url, name, threshold, currency, alert_email, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (url, name, threshold, currency, alert_email, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_product(product_id: int) -> Optional[dict]:
    """Fetch a single product by ID. Returns None if not found."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_product_by_url(url: str) -> Optional[dict]:
    """Fetch a product by its URL."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_products() -> list[dict]:
    """Return all tracked products ordered by creation date (newest first)."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_product(product_id: int, **fields) -> None:
    """
    Update arbitrary fields on a product row.
    Accepted keys: name, threshold, currency, last_price, alert_email.
    """
    allowed = {"name", "threshold", "currency", "last_price", "alert_email"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [product_id]

    conn = get_connection()
    try:
        conn.execute(f"UPDATE products SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def remove_product(product_id: int) -> bool:
    """Delete a product and its price history. Returns True if a row was deleted."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Price History
# ---------------------------------------------------------------------------

def add_price_record(product_id: int, price: float) -> int:
    """Record a price check. Returns the new record ID."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO price_history (product_id, price, checked_at) VALUES (?, ?, ?)",
            (product_id, price, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_price_history(product_id: int, limit: int = 20) -> list[dict]:
    """
    Return recent price records for a product, newest first.
    Default limit is 20 entries.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM price_history
            WHERE product_id = ?
            ORDER BY checked_at DESC
            LIMIT ?
            """,
            (product_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_price(product_id: int) -> Optional[float]:
    """Return the most recently recorded price for a product, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT price FROM price_history
            WHERE product_id = ?
            ORDER BY checked_at DESC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()
        return row["price"] if row else None
    finally:
        conn.close()
