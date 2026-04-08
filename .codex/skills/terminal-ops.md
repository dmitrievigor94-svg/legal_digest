# terminal-ops

Origin: adapted from Everything Claude Code (ECC)

Use when:

- the task depends on real command output
- verifying runtime behavior
- checking git state
- doing local operational validation

Core rules:

- inspect before editing
- report what was actually run
- distinguish changed locally, verified locally, committed, and pushed
- do not claim a fix without rerunning the proving command

Project-specific guidance:

- typical proving commands in this repo are:
  - `python -m unittest discover -s tests -v`
  - `python -m app.web`
  - `python -m app.cli ...`
  - local DB migration and digest smoke checks
