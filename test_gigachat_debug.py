# test_gigachat_debug.py
from __future__ import annotations

import os
import urllib3
urllib3.disable_warnings()

from dotenv import load_dotenv
load_dotenv()

import httpx

auth_key = os.environ.get("GIGACHAT_AUTH_KEY", "")
if not auth_key:
    print("❌ GIGACHAT_AUTH_KEY не найден в .env")
    exit(1)

print(f"Auth Key длина: {len(auth_key)}")
print()

print("=== Шаг 1: получаем токен ===")
try:
    resp = httpx.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": "0deeb919-bfd8-45ed-a502-13eba6f85498",
            "Authorization": f"Basic {auth_key}",
        },
        data={"scope": "GIGACHAT_API_PERS"},  # словарь как в документации
        verify=False,
        timeout=15,
    )
    print(f"Статус: {resp.status_code}")
    print(f"Ответ: {resp.text[:500]}")
except Exception as e:
    print(f"Ошибка: {e}")
    exit(1)

if resp.status_code != 200:
    print("❌ Не удалось получить токен")
    exit(1)

token = resp.json().get("access_token", "")
print(f"✓ Токен: {token[:20]}...")
print()

print("=== Шаг 2: тестовый запрос ===")
try:
    resp2 = httpx.post(
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": "GigaChat",
            "max_tokens": 50,
            "messages": [
                {"role": "user", "content": "Ответь одним словом: привет"}
            ],
        },
        verify=False,
        timeout=20,
    )
    print(f"Статус: {resp2.status_code}")
    print(f"Ответ: {resp2.text[:300]}")
except Exception as e:
    print(f"Ошибка: {e}")
    exit(1)

if resp2.status_code == 200:
    answer = resp2.json()["choices"][0]["message"]["content"]
    print(f"✓ GigaChat ответил: {answer}")
else:
    print("❌ Ошибка запроса к GigaChat")