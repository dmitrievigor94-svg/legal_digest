# AGENTS.md

This repository supports both Claude Code and Codex.

Codex should use this file as the project entry point, while Claude Code may continue to rely on `CLAUDE.md` and `.claude/`.

## Shared Context

Start with the shared project context in [docs/agent-context.md](/Users/igor/Projects/legal_digest/docs/agent-context.md).

That file contains:

- project purpose
- operational commands
- architecture
- editorial rules
- web panel intent
- coexistence rules for Codex and Claude

## Codex Guidance

Project-specific expectations for Codex:

- do not modify `CLAUDE.md` or `.claude/` unless explicitly asked
- prefer updating shared project facts in [docs/agent-context.md](/Users/igor/Projects/legal_digest/docs/agent-context.md)
- treat the web panel as an operator control panel, not a passive admin table
- preserve the single-tag rule
- preserve the `ArticleReview` history model when changing editorial flows
- treat sent-digest selection as production-sensitive logic

## Suggested Specialist Roles

If using role-style subagents or mental modes, the most useful project roles are:

- editorial-review
- pipeline-ops
- ui-workbench

See the project-local role notes in `.codex/agents/`.
