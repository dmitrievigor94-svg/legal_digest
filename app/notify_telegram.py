# app/notify_telegram.py
import os
import time as _time
import httpx

TG_API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000


def _split_html_text(text: str, max_len: int = MAX_LEN):
    if len(text) <= max_len:
        return [text]

    parts = []
    while len(text) > max_len:
        cut = text.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


def send_telegram_message_html(text: str, disable_preview: bool = True) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])

    url = TG_API.format(token=token, method="sendMessage")
    chunks = _split_html_text(text)

    with httpx.Client(timeout=25) as client:
        for chunk in chunks:
            # Fix #17: retry на 429 (Telegram rate limit)
            for attempt in range(4):
                resp = client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": disable_preview,
                    },
                )
                if resp.status_code == 429:
                    retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                    print(f"[TG] rate limit, ждём {retry_after}с (попытка {attempt+1}/4)")
                    _time.sleep(retry_after + 1)
                    continue
                resp.raise_for_status()
                break
            else:
                raise RuntimeError("[TG] не удалось отправить сообщение после 4 попыток (rate limit)")