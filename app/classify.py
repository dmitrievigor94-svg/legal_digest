# app/classify.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

LAW_DRAFT = "LAW_DRAFT"
LAW_ADOPTED = "LAW_ADOPTED"
GUIDANCE = "GUIDANCE"
ENFORCEMENT = "ENFORCEMENT"
COURTS = "COURTS"
MARKET = "MARKET_CASES"

pdn = "pdn"
ip = "ip"
consumers = "consumers"
advertising = "advertising"
competition = "competition"
banking = "banking"
telecom = "telecom"
it_platforms = "it_platforms"
cybersecurity = "cybersecurity"


def _m(pat: str, s: str) -> bool:
    return re.search(pat, s, flags=re.I) is not None


def _any(pats: Iterable[str], s: str) -> bool:
    return any(_m(p, s) for p in pats)


OFFICIAL_SOURCES = {
    "fas_news", "fas_acts", "fas_clarifications", "fas_analytics",
    "cbr_events", "cbr_press",
    "rkn_news",
    "pravo_gov", "regulation_gov",
}

MEDIA_SOURCES = {
    "fas_media",
    "drussia_all",
    "rapsi_judicial",
    "rapsi_publications",
}


def _is_official(source_id: str) -> bool:
    return source_id in OFFICIAL_SOURCES


def _is_media(source_id: str) -> bool:
    return source_id in MEDIA_SOURCES or source_id.startswith(("rapsi_", "drussia_"))


# --- UNIVERSAL HARD DENY ---
HARD_DENY_ALWAYS = [
    # война/геополитика
    r"\bвсу\b|\bсво\b|\bиран\b|\bтегеран\b|\bизраил\w*\b|\bсша\b.*\bнападени\w*\b",

    # криминал/уголовка/приговоры/аресты
    r"\bприговор(ил|ен|)\b|\bколони(я|и)\b|\bлишени(е|я)\s+свобод\w*\b",
    r"\bарест(овал|ован|ованы|)\b|\bзаключен(ие|ия)\s+под\s+страж\w*\b",
    r"\bвозбуд(ил|или)\s+уголовн\w*\s+дело\b|\bуголовн\w*\s+дело\b",
    r"\bтерроризм\b|\bтеракт\b|\bпризыв\w*\s+к\s+терроризм\w*\b",
    r"\bмошеннич\b|\bкраж\b|\bграбеж\b|\bвымогател\w*\b|\bвзятк\w*\b",
    r"\bнапавш\w*\s+с\s+ножом\b|\bубийств\b|\bизнасил\b|\bвзрыв\b",

    # персональная судебка
    r"\bзапрет\w*\s+на\s+выезд\b|\bна\s+выезд\s+из\s+рф\b",
    r"\bпродлен\w*\s+арест\b|\bпродлен\w*\s+содержан\w*\s+под\s+страж\w*\b",
    r"\b(иноагент\w*|уклонени\w*\s+от\s+обязанност\w*\s+иноагент\w*)\b",

    # ВОВ/памятники/осквернение
    r"\bосквернен\w*\b.*\bпамятник\w*\b|\bпамятник\w*\b.*\bвов\b|\bвов\b.*\bпамятник\w*\b",

    # бытовуха
    r"\bмногодетн\w*\b|\bматеринск\w*\s+капитал\b|\bалименты\b|\bопек\w*\b",
    r"\bегэ\b|\bгимназ\w*\b|\bшкол\w*\b|\bкласс\b",
    r"\bтурист\w*\b|\bотел\w*\b|\bгрязн\w*\s+номер\b",
    r"\bсвин(ь|ей)\b|\bпесочниц\w*\b|\bбродяч\w*\s+собак\w*\b|\bсамовыгул\b",
    r"\bоскорблен\w*\b.*\b(коридор|зале\s+суда)\b",

    # то, что ты отдельно попросил не брать
    r"\bлишени\w*\s+статус\w*\s+арбитр\w*\b",
    r"\bпо\s+делу\s+о\s+проверке\s+конституционност\w*.*\bналогов\w*\s+кодекс\w*\b",

    # новое: мелкая ерунда / таможенная бытовуха
    r"\bперекрывш\w*\s+дорог\w*\s+мусоровоз\w*\b",
    r"\bметеорит\w*\b.*\bдуба\w*\b|\bдронино\b.*\bдуба\w*\b",
]

PROTO_DENY = [
    r"\b(назначил\w*|назначен\w*|назначены|утвердил\w*|утвержден\w*)\b.*\b(судь\w*|зампред\w*|председател\w*|руководител\w*|начальник\w*)\b",
    r"\b(представил\w*|представлени\w*)\b.*\b(руководител\w*|начальник\w*|глав\w*\s+управлен\w*|губернатор\w*)\b",
    r"\b(поздравил\w*|поздравлени\w*|пожелал\w*|приветстви\w*)\b",
    r"\b(наградил\w*|награжден\w*|вручил\w*\s+награду)\b",
    r"\b(торжественн\w*|церемони\w*|юбиле\w*|годовщин\w*)\b",

    # что ты не хочешь видеть в дайджесте
    r"\bзаседани\w*\s+правительств\w*\b",
    r"\bматериал\w*\s+к\s+заседани\w*\s+правительств\w*\b",
    r"\bэкспертн\w*\s+совет\w*\b",
    r"\bзаседани\w*\s+коллеги\w*\b",
]

REPORTING_DENY = [
    r"\bитоги\b.*\b(года|за\s+\d{4})\b",
    r"\bза\s+\d{4}\s+год\b",
    r"\bитоги\s+работы\b",
    r"\bрезультаты\s+работы\b",
]

GENERAL_NOISE_DENY = [
    r"\b(совещан\w*|встрече\s+с|конференц\w*|форум\w*|выставк\w*|кругл(ый|ого)\s+стол)\b",
    r"\b(день\s+[а-я]+|недел[яи]\s+[а-я]+)\b",
    r"\b(тематическ\w*\s+цикл|материал\w*\s+цикл|историческ\w*|в\s+\d+\s+материал\w*)\b",
]


RE_LAW_ADOPTED = re.compile(
    r"\b("
    r"официальн(ое|ого)\s+опубликован|вступа(ет|ют)\s+в\s+силу|"
    r"федеральн(ый|ого)\s+закон|"
    r"постановлени(е|я)\s+правительств|"
    r"указ\s+президент|"
    r"зарегистрирован\w*\s+в\s+минюст"
    r")\b",
    re.I,
)

RE_LAW_DRAFT = re.compile(
    r"\b("
    r"законопроект|внесен\s+в\s+госдум|"
    r"проект\s+нпа|проект\s+фз|"
    r"публичн(ое|ого)\s+обсуждени|"
    r"общественн(ые|ых)\s+консультац|"
    r"проект\s+постановлени|проект\s+приказа"
    r")\b",
    re.I,
)

RE_GUIDANCE = re.compile(
    r"\b("
    r"разъяснен\w*|информационн(ое|ого)\s+письм|"
    r"вопросы\s+и\s+ответы|обзор\s+практик|"
    r"методич\w*|рекомендац\w*|позици(я|и)|памятк\w*|"
    r"фас\s+(заявил|сообщил|разъяснил)|"
    r"цб\s+(призвал|сообщил|разъяснил)|"
    r"банк\s+россии\s+(сообщил|разъяснил|рекомендует)"
    r")\b",
    re.I,
)

RE_ENFORCEMENT = re.compile(
    r"\b("
    r"штраф\w*|оштрафова\w*|привлечен\w*|привлекл\w*|"
    r"предписан\w*|предупрежден\w*|"
    r"исполнил(а|о|и)?\s+предупрежден\w*|"
    r"возбудил(а|о)\s+дело|дело\s+возбуждено|"
    r"провер(ит|к[аи]|я|ила|или)\b|"
    r"выявил(а|о)\b.*\b(признак\w*|нарушени\w*)|"
    r"выдал(а|о)\s+предписан\w*"
    r")\b",
    re.I,
)

RE_COURTS = re.compile(
    r"\b("
    r"верховн(ый|ого)\s+суд|конституционн(ый|ого)\s+суд|"
    r"арбитраж\w*|апелляц\w*|кассац\w*|"
    r"решени(е|я)\b|определени\w*|постановлени\w*|"
    r"иск\b|исков\w*\s+заявлени\w*|жалоб(а|у)\b|"
    r"не\s+пересмотрит|оставил\s+в\s+силе|"
    r"заблокировал\w*|блокировк\w*|ограничил\w*\s+доступ|"
    r"банкротств\w*|дело\s*№|"
    r"\bзащитил\s+покупател\w*\b|\bдополнительн\w*\s+пошлин\w*\b"
    r")\b",
    re.I,
)

RE_ENF_STRONG_VERB = re.compile(
    r"\b("
    r"оштрафова\w*|штраф\w*|"
    r"предписан\w*|предупрежден\w*|"
    r"исполнил(а|о|и)?\s+предупрежден\w*|"
    r"возбудил(а|о)\s+дело|дело\s+возбуждено"
    r")\b",
    re.I,
)

RE_PDN = re.compile(r"\b(персональн(ые|ых)\s+данн\w*|152(?:-| )?фз|роскомнадзор|утечк\w*|биометри\w*)\b", re.I)
RE_IP = re.compile(r"\b(товарн\w*\s+знак|патент\w*|авторск\w*\s+прав\w*|роспатент|сип\b|интеллектуальн\w*\s+собственност\w*)\b", re.I)
RE_COMP = re.compile(r"\b(конкуренц\w*|антимонопольн\w*|доминирован\w*|картел\w*|торг(и|ов)\b|закупк\w*|преференц\w*)\b", re.I)
RE_ADS = re.compile(r"\b(реклам\w*|маркировк\w*)\b", re.I)
RE_BANK = re.compile(
    r"\b("
    r"банк\s+россии|центральн\w*\s+банк|цб\b|санкц\w*|euroclear|clearstream|"
    r"блокировк\w*\s+счет\w*|блокировк\w*\s+сч[её]т\w*|"
    r"причин\w*\s+блокиров\w*\s+счет\w*|"
    r"115(?:-| )?фз|антиотмывоч\w*|финмониторинг\w*"
    r")\b",
    re.I,
)
RE_TELCO = re.compile(r"\b(оператор(ы)?\s+связи|абонентск\w*\s+номер\w*|нумерац\w*)\b", re.I)
RE_IT = re.compile(r"\b(маркетплейс\w*|агрегатор\w*|платформ\w*|онлайн[-\s]?сервис\w*|wheely|google|apple|iphone|telegram|телеграм)\b", re.I)
RE_CYBER = re.compile(r"\b(информационн\w*\s+безопасност\w*|фстэк\b|уязвимост\w*|взлом\w*|вирусн\w*\s+программ\w*)\b", re.I)


CBR_ROUTINE_DENY = [
    r"\bрезультаты\s+мониторинга\s+максимальн\w*\s+процентн\w*\s+ставок\b",
    r"\bинфляционн\w*\s+ожидани\w*\b",
    r"\bкорпоративн\w*\s+кредитовани\w*\b",
    r"\bтехническ\w*\s+работ\w*\b",
]


MARKET_STRONG_SIGNALS = [
    r"\b\d+\s*(млрд|трлн)\b",
    r"\b(санкц\w*|ограничен\w*|комплаенс\w*|риски?)\b",
    r"\b(фас\b|роскомнадзор\b|роспотребнадзор\w*|фнс\b|прокуратур\w*|минюст\w*)\b",
    r"\b(маркетплейс\w*|платформ\w*|агрегатор\w*|онлайн[-\s]?сервис\w*)\b",
    r"\b(предупрежден\w*|предписан\w*|провер(к|я|ка)|нарушени\w*|дело\s+возбуждено)\b",
    r"\b(блокировк\w*\s+счет\w*|115(?:-| )?фз|финмониторинг\w*)\b",
    r"\b(фас\s+(заявил|сообщил|разъяснил)|цб\s+(призвал|сообщил|разъяснил))\b",
]

MARKET_JUNK_SIGNALS = [
    r"\b(доверительн\w*\s+управлени\w*|передал\w*\s+в\s+управлени\w*)\b",
    r"\b(итоги|завершен\w*\s+переход|созда(ет|ют)ся\s+механизм|проработать\s+вопрос)\b",
    r"\b(выделен\w*\s+\d+|господдержк\w*|субсид\w*)\b",
]

CONSULTANT_ALLOWED_TAGS = {pdn, advertising, competition, telecom, it_platforms, cybersecurity, banking}

CONSULTANT_ALLOWLIST_PATTERNS = [
    r"\bиспользовани\w*\s+русск\w*\s+язык\w*\b.*\bгосударственн\w*\s+язык\w*\b",
    r"\bрусск\w*\s+язык\w*\b.*\bгосударственн\w*\s+язык\w*\b",
    r"\bроспотребнадзор\w*\b.*\bрусск\w*\s+язык\w*\b",
]

CONSULTANT_JUNK_HINTS = [
    r"\bпереч(ень|ни)\s+документ\w*\b",
    r"\bквалификационн\w*\s+экзамен\w*\b",
    r"\bуровн(и|ей)\s+кредитн\w*\s+рейтинг\w*\b",
    r"\bфонд\s+пенсионн\w*\b|\bсоциальн\w*\s+страховани\w*\b",
    r"\bфедеральн\w*\s+авиационн\w*\s+правил\w*\b",
    r"\bпо\s+делу\s+о\s+проверке\s+конституционност\w*.*\bналогов\w*\s+кодекс\w*\b",
]

def _consultant_should_keep(source_id: str, s: str, event: str, tags: list[str]) -> bool:
    if not source_id.startswith("consultant_"):
        return True

    if _any(CONSULTANT_ALLOWLIST_PATTERNS, s):
        return True

    if any(t in CONSULTANT_ALLOWED_TAGS for t in tags):
        return True

    return False


def _threshold(source_id: str, event: str) -> int:
    if _is_official(source_id):
        if event in (LAW_ADOPTED, LAW_DRAFT, ENFORCEMENT, GUIDANCE):
            return 2
        if event == COURTS:
            return 3
        return 4

    if source_id.startswith("rapsi_"):
        if event in (COURTS, ENFORCEMENT, LAW_ADOPTED, LAW_DRAFT, GUIDANCE):
            return 5
        return 7

    if source_id.startswith("drussia_") or source_id == "fas_media":
        return 7

    return 6


def _detect_event(source_id: str, s: str) -> str:
    # служебные форматы не должны превращаться в COURTS/GUIDANCE
    if _any(
        [
            r"\bзаседани\w*\s+правительств\w*\b",
            r"\bматериал\w*\s+к\s+заседани\w*\s+правительств\w*\b",
            r"\bэкспертн\w*\s+совет\w*\b",
            r"\bзаседани\w*\s+коллеги\w*\b",
        ],
        s,
    ):
        return MARKET

    # спец. правило: позиция ФАС по рекламе/телеграму — это guidance
    if _m(r"\bфас\s+(заявил|сообщил|разъяснил)\b", s) and (RE_ADS.search(s) or RE_IT.search(s)):
        return GUIDANCE

    # спец. правило: защита покупателя / доп.пошлина — это courts
    if _m(r"\bзащитил\s+покупател\w*\b", s) or _m(r"\bдополнительн\w*\s+пошлин\w*\b", s):
        return COURTS

    # приоритет судебных решений
    if _any(
        [
            r"\b(верховн(ый|ого)\s+суд|вс(?:\s+рф)?|конституционн(ый|ого)\s+суд|кс(?:\s+рф)?|арбитраж\w*|суд)\b"
            r".{0,80}"
            r"\b(признал|отменил|оставил\s+в\s+силе|не\s+пересмотрит|обязал|взыскал|разъяснил|защитил)\b",

            r"\b(признал|отменил|оставил\s+в\s+силе|не\s+пересмотрит|обязал|взыскал|разъяснил|защитил)\b"
            r".{0,80}"
            r"\b(верховн(ый|ого)\s+суд|вс\s+рф|конституционн(ый|ого)\s+суд|кс\s+рф|арбитраж\w*|суд)\b",
        ],
        s,
    ):
        return COURTS    

    if RE_LAW_ADOPTED.search(s):
        return LAW_ADOPTED
    if RE_LAW_DRAFT.search(s):
        return LAW_DRAFT
    if RE_GUIDANCE.search(s):
        return GUIDANCE
    if RE_COURTS.search(s):
        return COURTS
    if RE_ENFORCEMENT.search(s):
        return ENFORCEMENT

    if source_id == "fas_acts":
        return LAW_ADOPTED
    if source_id == "fas_clarifications":
        return GUIDANCE
    if source_id in ("cbr_press", "cbr_events"):
        return GUIDANCE

    return MARKET


def _extract_tags_and_boost(s: str) -> tuple[list[str], int]:
    tags: list[str] = []
    boost = 0

    if RE_PDN.search(s):
        tags.append(pdn); boost += 3
    if RE_IP.search(s):
        tags.append(ip); boost += 3
    if RE_COMP.search(s):
        tags.append(competition); boost += 2
    if RE_ADS.search(s):
        tags.append(advertising); boost += 2
    if RE_BANK.search(s):
        tags.append(banking); boost += 2
    if RE_TELCO.search(s):
        tags.append(telecom); boost += 2
    if RE_IT.search(s):
        tags.append(it_platforms); boost += 2
    if RE_CYBER.search(s):
        tags.append(cybersecurity); boost += 2

    if _m(r"\bфас\s+(заявил|сообщил|разъяснил)\b", s) and (RE_ADS.search(s) or RE_IT.search(s)):
        boost += 2

    if _m(r"\b(блокировк\w*\s+счет\w*|115(?:-| )?фз|финмониторинг\w*)\b", s):
        boost += 2

    return tags, boost


def _score_base(source_id: str, event: str) -> int:
    score = 0
    score += 2 if _is_official(source_id) else 0
    score += 0 if _is_media(source_id) else 1

    if event in (LAW_ADOPTED, LAW_DRAFT):
        score += 4
    elif event == ENFORCEMENT:
        score += 4
    elif event == COURTS:
        score += 4
    elif event == GUIDANCE:
        score += 3
    else:
        score += 1

    return score


def _market_is_keepable(source_id: str, s: str, tags: list[str]) -> bool:
    if _any(MARKET_JUNK_SIGNALS, s) and not tags:
        return False

    if _any(
        [
            r"\bзаседани\w*\s+правительств\w*\b",
            r"\bматериал\w*\s+к\s+заседани\w*\s+правительств\w*\b",
            r"\bэкспертн\w*\s+совет\w*\b",
            r"\bзаседани\w*\s+коллеги\w*\b",
            r"\bлишени\w*\s+статус\w*\s+арбитр\w*\b",
            r"\bперекрывш\w*\s+дорог\w*\s+мусоровоз\w*\b",
            r"\bметеорит\w*\b.*\bдуба\w*\b|\bдронино\b.*\bдуба\w*\b",
        ],
        s,
    ):
        return False

    if tags:
        return True

    if _any(MARKET_STRONG_SIGNALS, s):
        return True

    return False


@dataclass(frozen=True)
class Classified:
    keep: bool
    score: int
    event_type: str
    tags: list[str]


def classify(source_id: str, title: str, text: str = "", url: str = "") -> Classified:
    s = f"{title or ''} {text or ''}".strip()

    if source_id in {"cbr_press", "cbr_events"} and _any(CBR_ROUTINE_DENY, s):
        return Classified(False, -10, GUIDANCE, [])

    if _any(HARD_DENY_ALWAYS, s):
        return Classified(False, -10, MARKET, [])

    if _any(PROTO_DENY, s) or _any(GENERAL_NOISE_DENY, s):
        return Classified(False, -10, MARKET, [])
    if _any(REPORTING_DENY, s) and _is_media(source_id):
        return Classified(False, -10, MARKET, [])

    event = _detect_event(source_id, s)
    tags, boost = _extract_tags_and_boost(s)

    if source_id.startswith("consultant_"):
        if _any(CONSULTANT_JUNK_HINTS, s) and not _any(CONSULTANT_ALLOWLIST_PATTERNS, s):
            return Classified(False, -10, event, tags)

        if not _consultant_should_keep(source_id, s, event, tags):
            return Classified(False, -10, event, tags)

    if event == MARKET and not _market_is_keepable(source_id, s, tags):
        return Classified(False, -10, MARKET, tags)

    score = _score_base(source_id, event) + boost

    if event == ENFORCEMENT and RE_ENF_STRONG_VERB.search(s):
        score += 1

    thr = _threshold(source_id, event)
    keep = score >= thr

    return Classified(keep, score, event, tags)