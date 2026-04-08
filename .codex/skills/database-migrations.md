# database-migrations

Origin: adapted from Everything Claude Code (ECC)

Use when:

- adding columns or tables
- backfilling data
- changing editorial or digest workflow state
- preparing server-safe schema rollout

Core rules:

- every schema change must be idempotent
- prefer forward-safe migrations
- separate schema changes from large data repairs when possible
- never assume an empty or clean production state
- do not silently discard historical data

Project-specific guidance:

- `app/migrate.py` is the current migration surface, so new changes must remain safe to rerun
- preserve old article data while upgrading statuses or tags
- if backfilling editorial history, keep provenance obvious
- production migration safety matters more than elegance
