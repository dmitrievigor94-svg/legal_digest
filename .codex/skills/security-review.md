# security-review

Origin: adapted from Everything Claude Code (ECC)

Use when:

- dealing with secrets
- adding inputs or forms
- introducing network integrations
- touching server or deployment logic

Core rules:

- no hardcoded secrets
- validate external input
- avoid unsafe shell patterns
- review operational changes before shipping

Project-specific guidance:

- `.env` values must stay out of code and git
- Telegram, GigaChat, and DB credentials remain environment-driven
- be careful with server-side admin endpoints and destructive operations
