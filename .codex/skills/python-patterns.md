# python-patterns

Origin: adapted from Everything Claude Code (ECC)

Use when:

- writing or refactoring Python code
- reviewing Python modules
- shaping module boundaries or helper APIs

Core rules:

- optimize for readability over cleverness
- use explicit names and straightforward control flow
- prefer modern type hints
- catch specific exceptions, not bare `except`
- keep side effects visible
- keep modules small and cohesive

Project-specific guidance:

- prefer small, operationally clear functions in pipeline code
- use typed return values for orchestration results
- preserve idempotency and inspectability in daily jobs
- avoid hidden mutation across pipeline stages
