"""
Удаляет из БД статьи источников rg_main и rpn_news,
чтобы при следующем запуске send_daily_digest они прошли
через обновлённый filtering.py заново.

Запуск:
    python purge_for_refilter.py
    python purge_for_refilter.py --dry-run   # только показать, не удалять
    python purge_for_refilter.py --sources rg_main rpn_news rapsi_judicial
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, select, func

from app.db import SessionLocal
from app.models import Article

DEFAULT_SOURCES = ["rg_main", "rpn_news"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Показать что будет удалено, не удалять")
    parser.add_argument("--all", action="store_true", help="Удалить статьи всех источников из БД")
    parser.add_argument("--sources", nargs="+", default=None,
                        help=f"source_id для удаления (default: {DEFAULT_SOURCES})")
    args = parser.parse_args()

    if args.all:
        # Берём все source_id которые реально есть в БД
        with SessionLocal() as db:
            sources = [row[0] for row in db.execute(
                select(Article.source_id).distinct()
            ).all()]
        if not sources:
            print("БД пуста, нечего удалять.")
            return
        print(f"--all: будут очищены все источники: {sources}")
    else:
        sources = args.sources if args.sources is not None else DEFAULT_SOURCES

    with SessionLocal() as db:
        for source_id in sources:
            count = db.execute(
                select(func.count()).where(Article.source_id == source_id)
            ).scalar_one()

            if count == 0:
                print(f"  {source_id}: нет статей в БД, пропускаем")
                continue

            if args.dry_run:
                # Показываем первые 10 заголовков для проверки
                samples = db.execute(
                    select(Article.title, Article.published_at)
                    .where(Article.source_id == source_id)
                    .order_by(Article.created_at.desc())
                    .limit(10)
                ).all()
                print(f"\n  [DRY-RUN] {source_id}: {count} статей будет удалено. Примеры:")
                for title, pub in samples:
                    pub_str = pub.strftime("%d.%m") if pub else "?"
                    print(f"    [{pub_str}] {title[:80]}")
            else:
                db.execute(delete(Article).where(Article.source_id == source_id))
                print(f"  {source_id}: удалено {count} статей")

        if not args.dry_run:
            db.commit()
            print("\nГотово. Запусти теперь:")
            print("  python -m app.send_daily_digest")
            print("  (статьи зафетчатся заново и пройдут через новый filtering.py)")
        else:
            print("\n[DRY-RUN] Ничего не удалено. Убери --dry-run чтобы применить.")


if __name__ == "__main__":
    main()