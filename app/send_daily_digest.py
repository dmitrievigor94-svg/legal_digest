from __future__ import annotations

from app.db import SessionLocal
from app.config import configure_logging
from app.migrate import main as migrate
from app.pipeline import run_full_pipeline


def main() -> None:
    configure_logging()
    migrate()
    with SessionLocal() as db:
        run_full_pipeline(db)


if __name__ == "__main__":
    main()
