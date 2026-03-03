import os
from typing import List
import httpx

TG_API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 3900

def _split_text(text: str, max_len: int = MAX_LEN) -> List[str]:
    text = text or ""
    if len(text) <= max_len:
        return [text]

    parts, cur, cur_len = [], [], 0
    for line in text.splitlines(True):
        if cur_len + len(line) > max_len and cur:
            parts.append("".join(cur))
            cur, cur_len = [], 0
        while len(line) > max_len:
            parts.append(line[:max_len])
            line = line[max_len:]
        cur.append(line)
        cur_len += len(line)

    if cur:
        parts.append("".join(cur))
    return parts

def send_telegram_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])

    url = TG_API.format(token=token, method="sendMessage")
    chunks = _split_text(text)

    with httpx.Client(timeout=20) as client:
        for chunk in chunks:
            resp = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()