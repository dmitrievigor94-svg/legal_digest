from __future__ import annotations

import argparse
import logging
from datetime import date

from app.config import configure_logging, settings
from app.db import SessionLocal
from app.migrate import main as migrate
from app.pipeline import (
    build_digest_step,
    run_classify_step,
    run_fetch_step,
    run_full_pipeline,
    send_digest_step,
)

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Legal Digest operational CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("fetch", help="Забрать новые статьи из источников")

    classify_parser = subparsers.add_parser("classify", help="Извлечь текст и классифицировать статьи")
    classify_parser.add_argument("--reclassify-all", action="store_true")
    classify_parser.add_argument("--reclassify-days", type=int, default=0)
    classify_parser.add_argument("--refetch-text", action="store_true")
    classify_parser.add_argument("--debug", action="store_true")
    classify_parser.add_argument("--debug-max", type=int, default=1000)

    digest_parser = subparsers.add_parser("digest", help="Собрать и опционально отправить дайджест")
    digest_parser.add_argument("--date", dest="digest_date", help="Дата дайджеста в формате YYYY-MM-DD")
    digest_parser.add_argument("--send", action="store_true", help="Сразу отправить дайджест в Telegram")

    subparsers.add_parser("run", help="Полный fetch -> classify -> digest -> send")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    configure_logging()
    migrate()

    with SessionLocal() as db:
        if args.command == "fetch":
            result = run_fetch_step(db)
            logger.info("FETCH RESULT: %s", result)
            return

        if args.command == "classify":
            settings.gigachat_auth_key
            result = run_classify_step(
                db,
                reclassify_all=args.reclassify_all,
                reclassify_days=args.reclassify_days,
                refetch_text=args.refetch_text,
                debug=args.debug,
                debug_max=args.debug_max,
            )
            logger.info("CLASSIFY RESULT: %s", result)
            return

        if args.command == "digest":
            digest_date = date.fromisoformat(args.digest_date) if args.digest_date else None
            result = build_digest_step(db, digest_date=digest_date)
            logger.info("DIGEST RESULT: sent_count=%s", result.sent_count)
            if args.send:
                settings.telegram_bot_token
                settings.telegram_chat_id
                send_digest_step(db, result)
            return

        if args.command == "run":
            summary = run_full_pipeline(db)
            logger.info("RUN RESULT: %s", summary)


if __name__ == "__main__":
    main()
