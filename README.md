# Parade

A daily email digest of newly funded companies and their open tech roles.

Every morning, Parade scrapes funding news from TechCrunch, Crunchbase, and VentureBeat, resolves each company's careers page, and emails you a formatted digest with what they do and what engineering/product/data roles they're hiring for.

---

## What it does

1. **Fetches funding news** from free RSS feeds (TechCrunch, Crunchbase News, VentureBeat), filtered to the last 24 hours
2. **Resolves company websites** by parsing the source article, then falling back to the Clearbit autocomplete API, then DuckDuckGo
3. **Finds careers pages** by probing common paths (`/careers`, `/jobs`, etc.) and detecting ATS redirects
4. **Scrapes open tech roles** using native JSON APIs for Lever, Greenhouse, and Ashby — with a generic HTML fallback for custom pages
5. **Sends a formatted HTML email** via Gmail SMTP with company summaries, funding info, and clickable job listings

---

## Example email

```
Parade Digest — March 12, 2026
15 newly funded companies · 43 open tech roles

Acme AI                                    $25M · Series A
Building agentic workflows for enterprise teams.
Source: TechCrunch article

OPEN ROLES
[Engineering]  Senior Backend Engineer       — Remote
[AI/ML]        ML Research Scientist         — San Francisco
[Product]      Product Manager, Platform     — New York

─────────────────────────────────────────────────────
FooBar Inc.                                $10M · Seed
...
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/Mister-Raggs/Parade.git
cd Parade

python3 -m venv digest/.venv
source digest/.venv/bin/activate
pip install -r digest/requirements.txt
```

### 2. Configure credentials

```bash
cp digest/.env.example digest/.env
```

Edit `digest/.env`:

```env
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
RECIPIENT_EMAIL=you@gmail.com
```

> **Gmail App Password** — your regular password won't work. Get one at:
> [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification → App Passwords

### 3. Run

```bash
python -m digest.main
```

---

## Automated daily runs (GitHub Actions)

The workflow in [`.github/workflows/digest.yml`](.github/workflows/digest.yml) runs every day at **8:00 AM UTC** (3 AM EST).

**Add these three secrets** to your repo at Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `GMAIL_USER` | your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-char App Password |
| `RECIPIENT_EMAIL` | where to send the digest |

To test manually: Actions tab → "Daily Funding Digest" → "Run workflow".

---

## Configuration

All settings are controlled via environment variables (or `digest/.env` locally):

| Variable | Default | Description |
|---|---|---|
| `MAX_COMPANIES` | `15` | Max companies per digest |
| `MAX_JOBS_PER_CO` | `5` | Max tech roles shown per company |
| `LOOKBACK_HOURS` | `24` | How far back to look for funding news |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout in seconds |

---

## Project structure

```
digest/
├── main.py                  # Entry point — orchestrates the full pipeline
├── config.py                # Environment-based configuration
├── models.py                # FundedCompany and JobListing dataclasses
├── utils.py                 # Shared HTTP session with retry logic
├── requirements.txt
├── .env.example
├── scrapers/
│   ├── rss_scraper.py       # Parses funding news from RSS feeds
│   ├── company_resolver.py  # Maps company name → website → careers URL
│   └── careers_scraper.py   # ATS-aware job scraper (Lever, Greenhouse, Ashby)
└── email_sender/
    ├── renderer.py          # Jinja2 HTML + plain text rendering
    ├── sender.py            # Gmail SMTP sender
    └── templates/
        └── digest.html      # HTML email template
```

---

## Data sources

- **Funding news**: [TechCrunch](https://techcrunch.com/category/funding/), [Crunchbase News](https://news.crunchbase.com), [VentureBeat](https://venturebeat.com)
- **Company resolution**: Article HTML parsing → [Clearbit Autocomplete API](https://clearbit.com/docs#autocomplete-api) (free) → DuckDuckGo
- **Jobs**: Lever API, Greenhouse API, Ashby API, generic HTML scraping

---

## License

MIT
