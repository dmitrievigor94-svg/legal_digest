# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Legal Digest is a Python background job that fetches Russian legal/regulatory news from RSS and HTML sources, classifies articles using GigaChat LLM, and sends a daily digest to a Telegram channel. No web server — it's a scheduled pipeline.

## Commands

```bash
# Setup
pip install -r requirements.txt
docker-compose up -d          # Start PostgreSQL
python -m app.migrate         # Initialize DB schema

# Run
python -m app.send_daily_digest

# Useful env overrides
DIGEST_DEBUG=1 python -m app.send_daily_digest
DIGEST_DATE=2026-03-15 python -m app.send_daily_digest
RECLASSIFY_ALL=1 python -m app.send_daily_digest
RECLASSIFY_DAYS=3 python -m app.send_daily_digest
REFETCH_TEXT=1 python -m app.send_daily_digest

# Utilities
python -m app.debug_rss                          # Debug RSS fetching
python purge_for_refilter.py --dry-run           # Preview DB purge
python purge_for_refilter.py --all               # Reset all articles for re-filtering
RESET_DB=1 python -m app.migrate                 # Drop and recreate schema
```

No linting or test suite is configured. Ad-hoc scripts `test_gigachat_debug.py` and `test_gemini.py` exist for manual LLM testing.

## Architecture

The pipeline runs in `app/send_daily_digest.py` and has 5 sequential phases:

1. **Fetch** (`fetch_rss.py`, `sources.py`) — pulls items from 16 sources (RSS via feedparser, or HTML via lxml/BeautifulSoup). Each source has a `cutoff_hours` window and `kind` ("rss"/"html").

2. **Early filter** (`filtering.py`) — fast regex deny/allow rules applied before saving to DB. Goal: cut obvious noise (war news, criminal trials, school events), pass ambiguous items to LLM.

3. **Enrich & classify** (`extract.py`, `classify_llm.py`) — fetches full article text via trafilatura, then sends to GigaChat. Returns structured JSON: `event_type`, `tags`, `score` (0–10), `keep` (bool), `summary`, `reason`. Also has fast-deny patterns to skip LLM call for obvious rejects.

4. **Build digest** (`digest.py`) — selects `keep=true` articles in the date window, groups by topic, formats as HTML for Telegram.

5. **Send** (`notify_telegram.py`) — posts to Telegram Bot API, marks articles with `sent_at`.

## Key Files

- `app/send_daily_digest.py` — main orchestrator; all env var flags handled here
- `app/sources.py` — source definitions (add/remove/tune sources here)
- `app/filtering.py` — regex pre-filter rules (tune to reduce LLM calls)
- `app/classify_llm.py` — GigaChat classification; system prompt defines relevant topics and target audience
- `app/models.py` — single `Article` SQLAlchemy model; `keep`, `score`, `event_type`, `tags`, `llm_summary` are set by LLM
- `app/config.py` — all env var reading (DB, Telegram, GigaChat, timezone)
- `app/migrate.py` — schema init/reset

## Environment Variables

```
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
GIGACHAT_AUTH_KEY
DIGEST_TZ   # default: Europe/Moscow
```

## Deployment

GitHub Actions (`/.github/workflows/daily.yml`) runs at 7 AM UTC daily via `python -m app.send_daily_digest`. Secrets mirror the env vars above plus `DATABASE_URL`.
