# Codex Project Layer

This directory adds a Codex-friendly layer to the project without changing Claude-specific files.

Contents:

- `agents/` contains lightweight role notes for recurring tasks

Design principle:

- shared project truth lives in [docs/agent-context.md](/Users/igor/Projects/legal_digest/docs/agent-context.md)
- Codex reads `AGENTS.md`
- Claude Code keeps using `CLAUDE.md` and `.claude/`

This setup is intentionally additive and should not interfere with Claude tooling.
