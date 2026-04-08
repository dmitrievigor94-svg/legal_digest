# Codex Supplement

This file supplements the root [AGENTS.md](/Users/igor/Projects/legal_digest/AGENTS.md) with Codex-specific project notes.

## Purpose

This project uses a lightweight, project-local Codex layer inspired by Everything Claude Code (ECC), without modifying the existing Claude Code setup.

## Local Skills

Project-local Codex skills live in `.codex/skills/`.

Current curated set:

- `python-patterns`
- `postgres-patterns`
- `database-migrations`
- `search-first`
- `documentation-lookup`
- `frontend-design`
- `security-review`
- `tdd-workflow`
- `terminal-ops`

These are adapted from ECC concepts and trimmed for relevance to `legal_digest`.

## Agent Roles

Project-local Codex roles live in `.codex/agents/`.

- `explorer` for read-only code tracing
- `reviewer` for correctness/security review
- `docs_researcher` for documentation verification

## Coexistence Rule

Do not treat this directory as a replacement for Claude Code configuration.

- Claude Code keeps using `CLAUDE.md` and `.claude/`
- Codex uses `AGENTS.md`, this file, and `.codex/`
- shared facts belong in [docs/agent-context.md](/Users/igor/Projects/legal_digest/docs/agent-context.md)
