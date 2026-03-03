# app/sources.py

SOURCES = [
    # --- ФАС ---
    {"kind": "rss", "source_id": "fas_news", "source_name": "ФАС — новости", "url": "https://fas.gov.ru/news.rss",
     "cutoff_hours": 48, "allow_no_date": False},

    # эти три — НЕ ежедневные, пусть режутся жестко (будут чаще 0 — и это нормально)
    {"kind": "rss", "source_id": "fas_acts", "source_name": "ФАС — НПА", "url": "https://fas.gov.ru/documents/acts.rss",
     "cutoff_hours": 72, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_clarifications", "source_name": "ФАС — разъяснения", "url": "https://fas.gov.ru/documents/clarifications.rss",
     "cutoff_hours": 72, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_analytics", "source_name": "ФАС — аналитика", "url": "https://fas.gov.ru/documents/analytics.rss",
     "cutoff_hours": 72, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_media", "source_name": "ФАС — в СМИ", "url": "https://fas.gov.ru/publications.rss",
     "cutoff_hours": 72, "allow_no_date": False},

    # --- Банк России ---
    {"kind": "rss", "source_id": "cbr_events", "source_name": "Банк России — новости/интервью/выступления", "url": "https://www.cbr.ru/rss/eventrss",
     "cutoff_hours": 72, "allow_no_date": False},

    {"kind": "rss", "source_id": "cbr_press", "source_name": "Банк России — пресс-релизы", "url": "https://www.cbr.ru/rss/RssPress",
     "cutoff_hours": 168, "allow_no_date": False},

    # --- Минюст ---
    {"kind": "rss", "source_id": "minjust_all", "source_name": "Минюст — все материалы", "url": "https://minjust.ru/ru/rss.xml",
     "cutoff_hours": 0, "allow_no_date": True},  # даты нет — сохраняем, восстановим позже со страницы

    # --- D-Russia ---
    {"kind": "rss", "source_id": "drussia_all", "source_name": "D-Russia — все новости", "url": "https://d-russia.ru/feed",
     "cutoff_hours": 72, "allow_no_date": False},
]