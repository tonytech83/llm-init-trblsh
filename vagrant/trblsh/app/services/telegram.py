from datetime import datetime
from typing import Any

import requests

from app.utils.config import BOT_TOKEN, CHAT_ID, TRBLSH_URL, TZ


def send_telegram(message: Any, incident_id: str) -> None:
    print(f"*** {datetime.now(tz=TZ)} - Sending llm analysis to Telegram")

    telegram_msg = [
        f"💻  {message['hostname']}",
        f"📡  {message['ip_address']}",
        f"⚙️  {message['failed_services']}",
        f"⏰  {message['time']}",
        f"🌍  {TRBLSH_URL}/alert/{incident_id}",
    ]

    print("-" * 80)
    print("\n".join(telegram_msg))
    print("-" * 80)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "\n".join(telegram_msg),
    }

    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
