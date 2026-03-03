# app/filtering.py
import re

# Общие “мусорные” паттерны (для любых источников)
EXCLUDE_TITLE_PATTERNS = [
    r"\bреестр\b",
    r"\bстатистик",
    r"\bвременн(ые|ых)\s+ряд",
    r"\bаукцион\b",
    r"\bрепо\b",
    r"\bмеждународн(ые|ых)\s+резерв",
    r"\bдинамическ(ие|их)\s+ряд",
    r"\bликвидност",
    r"\bкарьера\b",
    r"\bинсайдерск(ая|ие)\s+информац",
    r"\bставк(а|и)\b.*\b(ruonia|miacr)\b",
    r"\bвалютн(ый|ые)\s+своп\b",
    r"\bобменн(ый|ые)\s+курс\b",
]

# Для ЦБ — разрешаем только явно “регуляторные” вещи
CBR_ALLOW_TITLE_HINTS = [
    "информационное письмо",
    "указание",
    "положение",
    "проект норматив",
    "публичного обсуждения",
    "общественных консультаций",
    "разъяснен",
    "письмо",
    "постановлен",
    "регламент",
    "санкц",
    "ограничен",
]

CBR_ALLOW_URL_HINTS = [
    "/Crosscut/LawActs/File/",
    "/Queries/UniDbQuery/File/",
    "/project_na/",
    "/press/pr/",
]

# D-Russia часто тащит “всё подряд”; оставим только то, что похоже на право/регуляторику/цифру в госе
DRUSSIA_ALLOW_HINTS = [
    "регулятор",
    "закон",
    "законопроект",
    "минцифры",
    "роскомнадзор",
    "персональн",
    "утечк",
    "госуслуг",
    "госзакуп",
    "фз",
    "нпа",
    "штраф",
    "суд",
    "комплаенс",
    "безопасност",
    "кибер",
    "ии",
    "идентификац",
    "крипто",
]

def is_relevant(source_id: str, title: str, url: str) -> bool:
    t = (title or "").strip().lower()
    u = (url or "").strip().lower()

    # жёсткие исключения (всем)
    for pat in EXCLUDE_TITLE_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE):
            return False

    # ЦБ: у тебя источники cbr_events и cbr_press (а не cbr_news)
    if source_id in ("cbr_events", "cbr_press"):
        for h in CBR_ALLOW_URL_HINTS:
            if h.lower() in u:
                return True
        for h in CBR_ALLOW_TITLE_HINTS:
            if h in t:
                return True
        return False

    # D-Russia: режем шум
    if source_id.startswith("drussia_"):
        return any(h in t for h in DRUSSIA_ALLOW_HINTS)

    # для остальных: если не попало в исключения — оставляем
    return True