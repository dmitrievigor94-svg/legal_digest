# app/sources.py

SOURCES = [
    # --- ФАС ---
    {"kind": "rss", "source_id": "fas_news", "source_name": "ФАС — новости",
     "url": "https://fas.gov.ru/news.rss", "cutoff_hours": 72, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_clarifications", "source_name": "ФАС — разъяснения",
     "url": "https://fas.gov.ru/documents/clarifications.rss", "cutoff_hours": 168, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_acts", "source_name": "ФАС — НПА",
     "url": "https://fas.gov.ru/documents/acts.rss", "cutoff_hours": 336, "allow_no_date": False},

    {"kind": "rss", "source_id": "fas_media", "source_name": "ФАС — в СМИ",
     "url": "https://fas.gov.ru/publications.rss", "cutoff_hours": 96, "allow_no_date": False},

    # --- ЦБ ---
    {"kind": "rss", "source_id": "cbr_events", "source_name": "Банк России — события",
     "url": "https://www.cbr.ru/rss/eventrss", "cutoff_hours": 168, "allow_no_date": False},

    {"kind": "rss", "source_id": "cbr_press", "source_name": "Банк России — пресс-релизы",
     "url": "https://www.cbr.ru/rss/RssPress", "cutoff_hours": 336, "allow_no_date": False},

    # --- РАПСИ ---
    {"kind": "rss", "source_id": "rapsi_judicial", "source_name": "РАПСИ — судебная информация",
     "url": "http://rapsinews.ru/export/rss2/judicial_information/index.xml", "cutoff_hours": 168, "allow_no_date": False},

    {"kind": "rss", "source_id": "rapsi_publications", "source_name": "РАПСИ — события дня (право)",
     "url": "http://rapsinews.ru/export/rss2/publications/index.xml", "cutoff_hours": 168, "allow_no_date": False},

    # --- Право.ru ---
    {"kind": "rss", "source_id": "pravo_ru", "source_name": "Право.ru — новости",
     "url": "https://pravo.ru/rss/", "cutoff_hours": 96, "allow_no_date": False},

    # --- D-Russia (шумный источник) ---
    {"kind": "rss", "source_id": "drussia_all", "source_name": "D-Russia — все новости",
     "url": "https://d-russia.ru/feed", "cutoff_hours": 96, "allow_no_date": False},

    # --- КонсультантПлюс ---
    {"kind": "rss", "source_id": "consultant_hotdocs", "source_name": "КонсультантПлюс — Горячие документы",
     "url": "https://www.consultant.ru/rss/hotdocs.xml", "cutoff_hours": 336, "allow_no_date": False},

    {"kind": "rss", "source_id": "consultant_law_news", "source_name": "КонсультантПлюс — Новости для юриста",
     "url": "https://www.consultant.ru/rss/nw.xml", "cutoff_hours": 336, "allow_no_date": False},

    {"kind": "rss", "source_id": "consultant_law_drafts", "source_name": "КонсультантПлюс — Обзор законопроектов",
     "url": "https://www.consultant.ru/rss/zw.xml", "cutoff_hours": 336, "allow_no_date": False},

    # --- ФТС ---
    {"kind": "rss", "source_id": "fts_news", "source_name": "ФТС — федеральные новости",
     "url": "https://customs.gov.ru/press/federal/rss", "cutoff_hours": 168, "allow_no_date": False},

         # --- Правительство РФ ---
    {"kind": "rss", "source_id": "gov_all", "source_name": "Правительство РФ — все материалы",
     "url": "http://government.ru/all/rss/", "cutoff_hours": 168, "allow_no_date": False},

    # --- Российская газета ---
    {"kind": "rss", "source_id": "rg_main", "source_name": "Российская газета — главная лента",
     "url": "https://rg.ru/xml/index.xml", "cutoff_hours": 168, "allow_no_date": False},

    # --- Роспотребнадзор (HTML, т.к. rss.php отдаёт HTML) ---
    {"kind": "html", "source_id": "rpn_news", "source_name": "Роспотребнадзор — новости",
    "url": "https://rospotrebnadzor.ru/region/rss/rss.php?type=special",
    "link_xpath": "//a[contains(@href,'ELEMENT_ID=')]",
    "base_url": "https://rospotrebnadzor.ru",
    "cutoff_hours": 168, "allow_no_date": True},

    # --- Экономика и жизнь ---
    {"kind": "rss", "source_id": "eg_online_news", "source_name": "Экономика и жизнь — новости",
     "url": "http://www.eg-online.ru/news/news_rss.php", "cutoff_hours": 168, "allow_no_date": False},
]