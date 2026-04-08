# search-first

Origin: adapted from Everything Claude Code (ECC)

Use when:

- starting a non-trivial feature
- considering a new dependency
- deciding whether to build or adopt

Workflow:

1. Check whether the repo already has the needed capability.
2. Check whether the language/framework already has a well-supported solution.
3. Only then write custom code.

Project-specific guidance:

- first search inside `app/` and `tests/` before adding helpers
- prefer existing pipeline and web abstractions over parallel ones
- avoid inventing a second operational path if the CLI or web panel already covers it
