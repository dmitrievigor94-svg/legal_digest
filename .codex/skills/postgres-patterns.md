# postgres-patterns

Origin: adapted from Everything Claude Code (ECC)

Use when:

- designing schema changes
- reviewing indexes
- troubleshooting query behavior
- deciding how to persist operational metadata

Core rules:

- prefer `timestamptz`-style timezone-aware timestamps
- use indexes intentionally, especially on workflow and filtering columns
- prefer partial or composite indexes when query shape clearly benefits
- avoid rewriting large tables casually
- separate query correctness from query speed concerns

Project-specific guidance:

- `articles` is an operational table, so keep filters on `keep`, `processing_status`, `sent_at`, and timestamps efficient
- new review/training tables should be append-only and queryable by article and time
- prefer additive changes over destructive ones
