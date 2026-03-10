# test_llm.py — запусти: python test_gemini.py
from __future__ import annotations

import os
import urllib3
urllib3.disable_warnings()

from dotenv import load_dotenv
load_dotenv()

from app.classify_llm import classify

auth_key = os.environ.get("GIGACHAT_AUTH_KEY", "")
if not auth_key:
    print("❌ GIGACHAT_AUTH_KEY не найден в .env")
    exit(1)

print(f"Auth Key найден: {auth_key[:10]}...")
print()

TEST_CASES = [
    ("fas_news",           "ФАС оштрафовала Wildberries на 1.5 млрд рублей за нарушение закона о рекламе",   True),
    ("cbr_press",          "Банк России разъяснил порядок блокировки счетов по 115-ФЗ",                       True),
    ("consultant_hotdocs", "Перечень документов для квалификационного экзамена нотариусов",                   False),
    ("fas_news",           "Поздравляем коллег с юбилеем ведомства",                                          False),
    ("rapsi_judicial",     "Верховный суд отменил решение о блокировке сайта по требованию правообладателя",  True),
    ("drussia_all",        "Суд наложил арест на счета компании в рамках антимонопольного дела",               True),
    ("fas_news",           "ЕГЭ 2024: расписание экзаменов опубликовано",                                     False),
]

print(f"Тестируем {len(TEST_CASES)} случаев...\n")

ok   = 0
fail = 0

for idx, (source_id, title, expected_keep) in enumerate(TEST_CASES, start=1):
    print(f"[{idx}/{len(TEST_CASES)}] {title[:65]}...")

    result = classify(source_id, title)

    status = "✓" if result.keep == expected_keep else "✗ НЕВЕРНО"
    if result.keep == expected_keep:
        ok += 1
    else:
        fail += 1

    print(f"  {status} | keep={result.keep} (ожидалось {expected_keep})")
    print(f"  [{result.event_type}] tags={result.tags}")
    print(f"  → {result.reason}")
    print()

print(f"Результат: {ok}/{len(TEST_CASES)} верно", "✓" if fail == 0 else f"| {fail} ошибок")