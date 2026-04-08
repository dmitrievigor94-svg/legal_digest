# tdd-workflow

Origin: adapted from Everything Claude Code (ECC)

Use when:

- adding features
- fixing bugs
- changing digest selection logic
- changing editorial workflows

Core rules:

- write or update the test that proves the behavior
- confirm the failing case before the fix when practical
- make the smallest useful change
- rerun the relevant test path after the fix

Project-specific guidance:

- for this repo, focus on unit/integration tests in `tests/`
- digest selection, tag normalization, and editorial actions should not change without regression coverage
- a tiny focused test is better than a broad brittle suite
