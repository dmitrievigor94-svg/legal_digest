# pipeline-ops

Use this role when working on:

- fetch/classify/build/send orchestration
- idempotency and re-runs
- digest windows
- migration safety
- production/server readiness

Key priorities:

- do not let already sent articles re-enter the next digest
- prefer small, reversible operational changes
- keep server migrations idempotent
- preserve local reproducibility
