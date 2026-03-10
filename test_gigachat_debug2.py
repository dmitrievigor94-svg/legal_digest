# test_gigachat_debug2.py
from __future__ import annotations

import os
import uuid
import urllib3
urllib3.disable_warnings()

from dotenv import load_dotenv
load_dotenv()

import httpx

auth_key = os.environ.get("GIGACHAT_AUTH_KEY", "")

# Шаг 1: токен
resp = httpx.post(
    "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
    headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": uuid.uuid4().hex,
        "Authorization": f"Basic {auth_key}",
    },
    data={"scope": "GIGACHAT_API_PERS"},
    verify=False,
    timeout=15,
)
print(f"Токен статус: {resp.status_code}")
token = resp.json()["access_token"]
print(f"Токен: {token[:20]}...")
print()

# Шаг 2: запрос с system промптом
print("=== Запрос с system промптом ===")
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
            {"role": "system", "content": "Отвечай только на русском."},
            {"role": "user",   "content": "Скажи привет"},
        ],
    },
    verify=False,
    timeout=20,
)
print(f"Статус: {resp2.status_code}")
print(f"Ответ: {resp2.text[:300]}")
if resp2.status_code == 200:
    print(f"✓ Ответ: {resp2.json()['choices'][0]['message']['content']}")