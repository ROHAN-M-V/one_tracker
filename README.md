# one_tracker

A full-stack price monitoring tool. Track e-commerce product prices, get email alerts when they drop below your target. Web dashboard + CLI.

## Features

**Scraping engine** — JSON-LD → Open Graph → CSS selectors → regex fallback. Playwright headless browser for JS-heavy sites (Amazon, Flipkart, Walmart). User-agent rotation, retry with exponential back-off.

**Web dashboard** — neo-brutalist UI, real-time product cards with status badges, SVG price history charts, toast notifications. Responsive.

**Backend** — Flask REST API, SQLite with WAL mode, background email alerts via SMTP, HTML email templates.

**Automation** — GitHub Actions daily cron job with database persistence via artifacts.

---

## Quick Start

```bash
git clone https://github.com/your-username/one_tracker.git
cd one_tracker
pip install -r requirements.txt
```

### Playwright (optional, for Amazon/Flipkart/Walmart)

```bash
pip install playwright
python -m playwright install chromium
```

### Email Alerts (optional)

```bash
cp .env.example .env
# Edit .env with your SMTP credentials (Gmail: use an App Password)
```

---

## Web Dashboard

```bash
python server.py
# → http://localhost:5000
```

| Action | How |
|--------|-----|
| Track a product | Enter URL + target price, click "Track This" |
| Check one product | Click refresh icon on any card |
| Check all | "Check All" button in header |
| Price history | "History" button → modal with chart + table |
| Delete | Trash icon on card |

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/products` | List all |
| `POST` | `/api/products` | Add product (`url`, `threshold`, `email`) |
| `GET` | `/api/products/:id` | Get one |
| `DELETE` | `/api/products/:id` | Remove |
| `POST` | `/api/products/:id/check` | Check price |
| `GET` | `/api/products/:id/history` | Price history (`?limit=N`) |
| `POST` | `/api/products/check-all` | Check all |

---

## CLI

```bash
python main.py add "https://www.amazon.com/dp/B07MGHB4Q3" 29.99
python main.py add "https://flipkart.com/product" 499 --email deals@example.com
python main.py check
python main.py check --id 7
python main.py list
python main.py history 7
python main.py history 7 --limit 50
python main.py remove 7 -f
```

| Command | Description |
|---------|-------------|
| `add <url> <threshold> [--email]` | Start tracking |
| `check [--id ID]` | Price check |
| `list` | Show all products |
| `history <id> [--limit N]` | Price history |
| `remove <id> [-f]` | Delete product |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | For email | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | For email | `587` | SMTP port |
| `SMTP_USER` | For email | — | Login email |
| `SMTP_PASSWORD` | For email | — | App password |
| `ALERT_EMAIL_FROM` | No | `SMTP_USER` | Sender address |
| `PRICE_TRACKER_DB` | No | `./price_tracker.db` | DB path |
| `PORT` | No | `5000` | Server port |

---

## GitHub Actions

Daily price checks at midnight UTC via `.github/workflows/price_check.yml`.

**Setup:** Push to GitHub → Settings → Secrets → add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`. The workflow persists the SQLite DB as an artifact (90-day retention).

---

## Project Structure

```
one_tracker/
├── server.py                 # Flask API + static serving
├── main.py                   # CLI (argparse)
├── requirements.txt
├── .env.example
├── src/
│   ├── scraper.py            # requests + Playwright scraping
│   ├── database.py           # SQLite layer
│   ├── alerter.py            # SMTP email alerts
│   └── utils.py              # URL validation, price parsing
├── static/
│   ├── index.html            # Web dashboard
│   ├── style.css             # Neo-brutalist theme
│   └── app.js                # Frontend logic
└── .github/workflows/
    └── price_check.yml       # Daily cron
```

---

## How It Works

```
URL + target price
       │
       ▼
Scraper fetches page
  ├─ Fast mode (requests) for static sites
  └─ Browser mode (Playwright) for JS-heavy sites
       │
       ▼
Price extracted (JSON-LD → meta → CSS → regex)
       │
       ▼
Stored in SQLite with timestamp
       │
       ▼
Price ≤ threshold → HTML email alert via SMTP
```

## Supported Sites

| Site | Mode | Notes |
|------|------|-------|
| Amazon (all regions) | Browser | Auto-cleans tracking URLs |
| Flipkart | Browser | — |
| Walmart | Browser | — |
| Best Buy | Browser | — |
| eBay | Browser | — |
| Target | Browser | — |
| Any site with JSON-LD | Fast | Best compatibility |
| Any site with visible prices | Fast | Regex fallback |

## Tech Stack

Python 3.12+ · Flask · SQLite · requests · BeautifulSoup4 · lxml · Playwright · Vanilla HTML/CSS/JS · Space Grotesk + JetBrains Mono · GitHub Actions

## License

MIT
