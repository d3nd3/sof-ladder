import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./sof_ladder.db")
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8080"))
    api_base: str = os.getenv("API_BASE", "http://127.0.0.1:8080")
    orchestrator_secret: str = os.getenv("ORCHESTRATOR_SECRET", "change-me")
    bot_api_secret: str = os.getenv("BOT_API_SECRET", "change-me-bot")
    match_offer_seconds: int = int(os.getenv("MATCH_OFFER_SECONDS", "60"))
    queue_max_minutes: int = int(os.getenv("QUEUE_MAX_MINUTES", "20"))
    elo_window_start: int = int(os.getenv("ELO_WINDOW_START", "50"))
    elo_window_cap: int = int(os.getenv("ELO_WINDOW_CAP", "300"))
    elo_window_grow: int = int(os.getenv("ELO_WINDOW_GROW", "50"))
    elo_window_interval: int = int(os.getenv("ELO_WINDOW_INTERVAL", "30"))
    fraglimit: int = int(os.getenv("FRAGLIMIT", "20"))
    server_connect_ip: str = os.getenv("SERVER_CONNECT_IP", "127.0.0.1")
    port_start: int = int(os.getenv("PORT_START", "28910"))
    port_end: int = int(os.getenv("PORT_END", "28959"))
    ladder_hub_enabled: bool = os.getenv("LADDER_HUB_ENABLED", "").lower() in ("1", "true", "yes")
    ladder_hub_port: int = int(os.getenv("LADDER_HUB_PORT", "28907"))


settings = Settings()
