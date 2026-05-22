import httpx
from ladder.config import settings


class ApiClient:
    def __init__(self):
        self.base = settings.api_base.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.bot_api_secret}"}

    async def _req(self, method: str, path: str, **kwargs):
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.request(method, f"{self.base}{path}", headers=self.headers, **kwargs)
            if r.status_code >= 400:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    detail = r.text
                raise RuntimeError(detail)
            return r.json() if r.content else {}

    async def link_start(self, discord_id: str):
        return await self._req("POST", "/players/link/start", json={"discord_id": discord_id})

    async def get_player(self, discord_id: str):
        return await self._req("GET", f"/players/{discord_id}")

    async def pending(self, discord_id: str):
        return await self._req("GET", f"/players/{discord_id}/pending")

    async def queue_join(self, discord_id: str):
        return await self._req("POST", "/queue/join", json={"discord_id": discord_id})

    async def queue_leave(self, discord_id: str):
        return await self._req("POST", "/queue/leave", json={"discord_id": discord_id})

    async def queue_count(self):
        return await self._req("GET", "/queue/count")

    async def accept(self, match_id: int, discord_id: str):
        return await self._req("POST", f"/matches/{match_id}/accept", json={"discord_id": discord_id})

    async def get_match(self, match_id: int):
        return await self._req("GET", f"/matches/{match_id}")

    async def leaderboard(self, limit: int = 15):
        return await self._req("GET", "/leaderboard", params={"limit": limit})

    async def pending_matches(self):
        return await self._req("GET", "/matches/pending")

    async def live_matches(self):
        return await self._req("GET", "/matches/live")
