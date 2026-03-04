# app/sources.py
SOURCES = [
    # --- ФАС ---
    {"kind": "rss", "source_id": "fas_news", "source_name": "ФАС — новости", "url": "https://fas.gov.ru/news.rss",
     "cutoff_hours": 72, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_clarifications", "source_name": "ФАС — разъяснения", "url": "https://fas.gov.ru/documents/clarifications.rss",
     "cutoff_hours": 168, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_acts", "source_name": "ФАС — НПА", "url": "https://fas.gov.ru/documents/acts.rss",
     "cutoff_hours": 336, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_media", "source_name": "ФАС — в СМИ", "url": "https://fas.gov.ru/publications.rss",
     "cutoff_hours": 96, "allow_no_date": False},

    # --- ЦБ ---
    {"kind": "rss", "source_id": "cbr_events", "source_name": "Банк России — события", "url": "https://www.cbr.ru/rss/eventrss",
     "cutoff_hours": 168, "allow_no_date": False},

    {"kind": "rss", "source_id": "cbr_press", "source_name": "Банк России — пресс-релизы", "url": "https://www.cbr.ru/rss/RssPress",
     "cutoff_hours": 336, "allow_no_date": False},

    # --- Официальное опубликование НПА ---
    # URL вы генерируете в RSS-конструкторе publication.pravo.gov.ru (можно сделать несколько лент по типам актов/органам).
    # Пока ставим placeholder — ты подставишь сгенеренный URL.
    #{"kind": "rss", "source_id": "pravo_gov", "source_name": "Официальное опубликование (pravo.gov.ru)", "url": "PASTE_RSS_URL_FROM_publication.pravo.gov.ru",
    # "cutoff_hours": 168, "allow_no_date": False},

    # --- РКН ---
    #{"kind": "rss", "source_id": "rkn_news", "source_name": "РКН — новости", "url": "PASTE_RSS_URL_FROM_rkn.gov.ru_subscribe",
    # "cutoff_hours": 168, "allow_no_date": False},

    # --- ФСТЭК ---
    {"kind": "rss", "source_id": "fstec_news", "source_name": "ФСТЭК — новости", "url": "https://fstec.ru/rss-lenta",
     "cutoff_hours": 336, "allow_no_date": False, "ssl_verify": False},

    # --- РАПСИ: судебка + право-кейсы ---
    {"kind": "rss", "source_id": "rapsi_judicial", "source_name": "РАПСИ — судебная информация", "url": "http://rapsinews.ru/export/rss2/judicial_information/index.xml",
     "cutoff_hours": 168, "allow_no_date": False},

    {"kind": "rss", "source_id": "rapsi_publications", "source_name": "РАПСИ — события дня (право)", "url": "http://rapsinews.ru/export/rss2/publications/index.xml",
     "cutoff_hours": 168, "allow_no_date": False},

    # --- D-Russia (строго через scoring) ---
    {"kind": "rss", "source_id": "drussia_all", "source_name": "D-Russia — все новости", "url": "https://d-russia.ru/feed",
     "cutoff_hours": 96, "allow_no_date": False},
]