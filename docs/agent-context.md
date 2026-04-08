# Agent Context

## Project

`legal_digest` is a Python service that:

- fetches Russian legal and regulatory news from RSS and HTML sources
- enriches articles with extracted text
- classifies them with GigaChat
- builds a Telegram digest
- exposes a local/editorial web panel for review and cleanup

The repo is used in production on a VPS and is also actively operated locally.

## Main Commands

```bash
# setup
pip install -r requirements.txt
docker compose up -d db
python -m app.migrate

# web panel
python -m app.web

# pipeline cli
python -m app.cli run
python -m app.cli fetch
python -m app.cli classify
python -m app.cli digest
python -m app.cli digest --send

# legacy entrypoint
python -m app.send_daily_digest
```

## Architecture

Core modules:

- `app/pipeline.py` orchestrates fetch, classify, build, send
- `app/cli.py` exposes the operational CLI
- `app/classify_llm.py` handles GigaChat classification
- `app/digest.py` selects digest candidates and formats output
- `app/web.py` is the editorial control panel
- `app/models.py` stores `Article` and manual review history in `ArticleReview`
- `app/migrate.py` performs idempotent schema upgrades

## Editorial Rules

These are product rules, not optional preferences:

- each article may have only one tag
- the tag defines the digest section
- `keep=True` articles must not remain without a valid tag
- already sent articles must not appear in the next digest selection
- manual corrections are valuable training data and should be preserved

Current fallback behavior:

- if classification returns `keep=True` with no valid tag, the system assigns `_other`

## Web Panel Intent

The web panel is not just a database viewer. It should serve three operational goals:

1. Prepare the next digest.
   The operator reviews upcoming candidates, fixes `keep`, `event_type`, and `tag`, and ensures the next issue is clean before sending.

2. Review past decisions.
   Already sent or older materials are used for retrospective cleanup: should we have taken this item, did it have the right type, did it have the right tag.

3. Capture training signals.
   Manual changes should be recorded so they can later be used to evaluate or fine-tune prompts/models.

Current UI concepts:

- `Подготовка выпуска` is the future-facing workspace
- `Архив и разбор` is the retrospective workspace
- `Следующий дайджест` is a focused widget for the upcoming issue
- `Отправленные дайджесты` is the archive entry point
- `Журнал ручных решений` stores manual overrides and bulk actions

## Data Notes

`ArticleReview` stores:

- article id
- action type
- review scope: `future` or `archive`
- previous and new values for `keep`, `event_type`, and primary tag
- timestamp

This table is intended to become the foundation for future model evaluation/training.

## Workflow Expectations

When editing this repo:

- prefer additive, idempotent migrations
- do not break the production pipeline for local UX improvements
- preserve compatibility with both Codex and Claude-oriented project files
- keep `CLAUDE.md` untouched unless explicitly asked
- put shared project knowledge in neutral project docs instead of duplicating large instructions in multiple tool-specific files

## Coexistence Policy

This project intentionally supports both Claude Code and Codex.

- `CLAUDE.md` remains the Claude-facing project file
- `AGENTS.md` is the Codex-facing project file
- this document is the shared context layer both can rely on

If future instructions diverge, the shared project facts in this file should be reconciled first, then mirrored into tool-specific adapters.
