import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("TOKEN", "")
CHAT_ID: str = os.getenv("CHAT_ID", "")
TZ = ZoneInfo(os.getenv("TIME_ZONE", "UTC"))

TRBLSH_URL = "http://192.168.56.15:8080"

OLLAMA_API = "http://192.168.0.88:11434/api/generate"
OLLAMA_REQUEST_TIMEOUT = 300
