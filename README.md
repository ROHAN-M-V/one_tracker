# 🏷️ Price Tracker

A lightweight Python CLI tool that monitors e-commerce product prices and sends email alerts when prices drop below your target threshold.

## Features

- **Multi-strategy price extraction** — JSON-LD, Open Graph, CSS selectors, regex fallback
- **Email alerts** — polished HTML notifications via SMTP when prices drop
- **SQLite storage** — zero-config local database for products and price history
- **User-agent rotation** — randomised headers with retry + exponential back-off
- **GitHub Actions** — automated daily price checks in the cloud
- **CLI interface** — simple commands: `add`, `check`, `list`, `history`, `remove`

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/your-username/price-tracker.git
cd price-tracker
pip install -r requirements.txt
```

### 2. Configure email alerts (optional)

```bash
cp .env.example .env
# Edit .env with your SMTP credentials
```

For **Gmail**, enable 2-Factor Authentication and create an [App Password](https://myaccount.google.com/apppasswords).

### 3. Track a product

```bash
# Add a product with a target price of $29.99
python main.py add "https://www.example.com/product-page" 29.99

# Optionally specify alert email
python main.py add "https://www.example.com/product" 49.99 --email deals@example.com
```

### 4. Check prices

```bash
# Check all tracked products
python main.py check

# Check a specific product
python main.py check --id 1
```

### 5. View history & manage

```bash
# List all tracked products
python main.py list

# View price history
python main.py history 1

# Remove a product
python main.py remove 1
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `add <url> <threshold>` | Start tracking a product |
| `check [--id ID]` | Run price check for all or one product |
| `list` | Show all tracked products |
| `history <id> [--limit N]` | Display price history (default: last 20) |
| `remove <id> [-f]` | Remove a product (`-f` to skip confirmation) |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | For email | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | For email | `587` | SMTP port |
| `SMTP_USER` | For email | — | Login email |
| `SMTP_PASSWORD` | For email | — | Login password / app password |
| `ALERT_EMAIL_FROM` | No | `SMTP_USER` | Override sender address |
| `PRICE_TRACKER_DB` | No | `./price_tracker.db` | Custom DB path |

## GitHub Actions (Automated Scheduling)

The included workflow (`.github/workflows/price_check.yml`) runs daily at midnight UTC.

### Setup

1. Push the repo to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add these repository secrets:
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASSWORD`
4. Add your products locally, then push the `price_tracker.db` file (or add products via a one-time workflow run)

The workflow persists the SQLite database as a GitHub artifact across runs.

## Project Structure

```
tracker/
├── src/
│   ├── __init__.py       # Package init
│   ├── scraper.py        # Web scraping + price extraction
│   ├── database.py       # SQLite storage layer
│   ├── alerter.py        # Email notification service
│   └── utils.py          # URL validation, price parsing
├── main.py               # CLI entry point
├── requirements.txt      # Python dependencies
├── .env.example          # Environment config template
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── price_check.yml  # GitHub Actions cron job
```

## How It Works

1. **You provide a URL and threshold** → the scraper fetches the page
2. **Price is extracted** using a 4-tier cascade:
   - Schema.org JSON-LD structured data
   - Open Graph / meta tags
   - Common CSS selectors (Amazon, Flipkart, Best Buy, etc.)
   - Regex pattern matching (fallback)
3. **Price is stored** in SQLite with a timestamp
4. **If price ≤ threshold** → an HTML email alert is sent
5. **GitHub Actions** re-runs this check daily automatically

## Supported Sites

The scraper works best with sites that include structured data (JSON-LD) or standard price markup. Tested patterns include:

- Amazon (US/IN)
- Flipkart
- Best Buy
- Walmart
- Any site with `itemprop="price"` or Schema.org Product markup

> **Note:** Sites with heavy JavaScript rendering or anti-bot measures may not work with the current static scraper. See [Known Limitations](#known-limitations).

## Known Limitations

- **JavaScript-rendered pages**: The scraper uses `requests` (no browser), so prices loaded via JavaScript won't be visible. Consider Playwright for dynamic pages.
- **Anti-scraping measures**: CAPTCHAs, IP blocking, and aggressive bot detection will prevent extraction.
- **Price format edge cases**: While the parser handles most formats ($, €, £, ₹, commas, dots), some unusual layouts may fail.
- **Single-user design**: The SQLite database is designed for local/single-user usage.

## License

MIT
