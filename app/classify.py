# app/classify.py
from __future__ import annotations

import re
from dataclasses import dataclass

# --- event types (для секций дайджеста) ---
LAW_DRAFT = "LAW_DRAFT"
LAW_ADOPTED = "LAW_ADOPTED"
GUIDANCE = "GUIDANCE"
ENFORCEMENT = "ENFORCEMENT"
COURTS = "COURTS"
MARKET = "MARKET_CASES"

# --- tags (предметка/отрасли) ---
pdn = "pdn"
ip = "ip"
consumers = "consumers"
advertising = "advertising"
competition = "competition"
banking = "banking"
telecom = "telecom"
it_platforms = "it_platforms"
cybersecurity = "cybersecurity"

# --- hard deny (общий мусор) ---
HARD_DENY = [
    r"\b(поздравл|награжден|торжественн|всемирн(ый|ого)\s+день|юбиле)\b",
    r"\b(совещан|встрече\s+с|конференц|форум|выставк|кругл(ый|ого)\s+стол)\b",
    r"\b(день\s+[а-я]+|недел[яи]\s+[а-я]+)\b",
]

RE_COURT = re.compile(r"\b(верховн(ый|ого)\s+суд|суд\s+по\s+интеллектуальн|арбитраж|апелляц|кассац|определени|постановлени|решени(е|я)|дело\s*№)\b", re.I)
RE_ENF = re.compile(r"\b(штраф|привлечен|возбудил(а|о)\s+дело|предписан|предупрежден|нарушени|административн(ое|ых)\s+правонарушен|провер(к|я))\b", re.I)
RE_ADOPTED = re.compile(r"\b(официальн(ое|ого)\s+опубликован|вступа(ет|ют)\s+в\s+силу|федеральн(ый|ого)\s+закон|постановлени(е|я)\s+правительств|указ\s+президент)\b", re.I)
RE_DRAFT = re.compile(r"\b(проект\s+нпа|проект\s+фз|публичн(ое|ого)\s+обсуждени|общественн(ые|ых)\s+консультац|законопроект|внесен\s+в\s+госдум)\b", re.I)
RE_GUIDE = re.compile(r"\b(разъяснен|информационн(ое|ого)\s+письм|письмо|позици(я|и)|рекомендац|методич|обзор\s+практик|вопросы\s+и\s+ответы)\b", re.I)

RE_PDN = re.compile(r"\b(персональн(ые|ых)\s+данн|152(?:-| )?фз|роскомнадзор|утечк|биометри|cookie|локализац|согласие\s+на\s+обработк)\b", re.I)
RE_IP = re.compile(r"\b(товарн(ый|ого)\s+знак|патент|авторск(ое|их)\s+прав|лицензионн|контрафакт|роспатент|сип|интеллектуальн(ая|ого)\s+собственност)\b", re.I)
RE_CONS = re.compile(r"\b(потребител|оферт|подписк|возврат|навязанн|дистанционн(ая|ые)\s+торговл|качество\s+услуг)\b", re.I)
RE_ADS = re.compile(r"\b(реклам|маркировк|недобросовестн(ая|ые)\s+реклам)\b", re.I)
RE_COMP = re.compile(r"\b(конкуренц|антимонопольн|доминирован|картел|торг(и|ов)|закупк)\b", re.I)
RE_BANK = re.compile(r"\b(банк\s+россии|банковск|кредитн(ая|ые)\s+организац|платеж|эквайр|нпс|финтех)\b", re.I)
RE_TELCO = re.compile(r"\b(оператор(ы)?\s+связи|связ(ь|и)|роуминг|межсетев|интерконнект|спам)\b", re.I)
RE_IT = re.compile(r"\b(маркетплейс|агрегатор|платформ|онлайн[-\s]?сервис|приложен|цифров(ая|ые)\s+платформ)\b", re.I)
RE_CYBER = re.compile(r"\b(кии|информационн(ая|ые)\s+безопасност|фстэк|криптограф|сертификац|уязвимост)\b", re.I)

OFFICIAL_SOURCES = {
    "fas_news", "fas_acts", "fas_clarifications", "fas_analytics", "fas_media",
    "cbr_events", "cbr_press",
    "rkn_news", "fstec_news", "pravo_gov", "regulation_gov",
}

MEDIA_SOURCES = {"drussia_all", "rapsi_judicial", "rapsi_publications"}

@dataclass(frozen=True)
class Classified:
    keep: bool
    score: int
    event_type: str
    tags: list[str]

def classify(source_id: str, title: str, text: str = "", url: str = "") -> Classified:
    s = f"{title or ''} {text or ''}".strip()

    # hard deny
    for pat in HARD_DENY:
        if re.search(pat, s, flags=re.I):
            return Classified(False, -10, MARKET, [])

    score = 0
    if source_id in OFFICIAL_SOURCES:
        score += 1

    # event type priority
    if RE_COURT.search(s):
        event = COURTS
        score += 3
    elif RE_ENF.search(s):
        event = ENFORCEMENT
        score += 3
    elif RE_ADOPTED.search(s):
        event = LAW_ADOPTED
        score += 3
    elif RE_DRAFT.search(s):
        event = LAW_DRAFT
        score += 3
    elif RE_GUIDE.search(s):
        event = GUIDANCE
        score += 2
    else:
        # source hints
        if source_id in ("cbr_press", "cbr_events", "fas_clarifications"):
            event = GUIDANCE
            score += 1
        else:
            event = MARKET

    tags: list[str] = []
    if RE_PDN.search(s): tags.append(pdn); score += 2
    if RE_IP.search(s): tags.append(ip); score += 2
    if RE_CONS.search(s): tags.append(consumers); score += 1
    if RE_ADS.search(s): tags.append(advertising); score += 1
    if RE_COMP.search(s): tags.append(competition); score += 1
    if RE_BANK.search(s): tags.append(banking); score += 1
    if RE_TELCO.search(s): tags.append(telecom); score += 1
    if RE_IT.search(s): tags.append(it_platforms); score += 1
    if RE_CYBER.search(s): tags.append(cybersecurity); score += 1

    # thresholds (средняя точность)
    # official: >=1 (мягко)
    # media: >=4 (жёстче, но не “в ноль”)
    if source_id in MEDIA_SOURCES:
        keep = score >= 4
    else:
        keep = score >= 1

    return Classified(keep, score, event, tags)