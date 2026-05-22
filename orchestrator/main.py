import asyncio
import os
from pathlib import Path

import httpx

from ladder.config import settings
from ladder.db import init_db
from ladder import services
from orchestrator.monitor import MatchRuntime, tick_match
from orchestrator.spawn import spawn_server

API = settings.api_base.rstrip("/")
ORCH_HEADERS = {"X-Orchestrator-Secret": settings.orchestrator_secret}
OUT_DIR = Path(os.getenv("SOF_LADDER_OUT_DIR", "/opt/sof/user/sofplus/data/ladder_out"))


class PortPool:
    def __init__(self):
        self.used: set[int] = set()

    def alloc(self) -> int | None:
        for p in range(settings.port_start, settings.port_end + 1):
            if p not in self.used:
                self.used.add(p)
                return p
        return None

    def free(self, port: int):
        self.used.discard(port)


async def api_get(client: httpx.AsyncClient, path: str):
    r = await client.get(f"{API}{path}", headers=ORCH_HEADERS)
    r.raise_for_status()
    return r.json()


async def api_post(client: httpx.AsyncClient, path: str, body: dict):
    r = await client.post(f"{API}{path}", headers=ORCH_HEADERS, json=body)
    r.raise_for_status()
    return r.json()


async def run_loop():
    init_db()
    pool = PortPool()
    runtimes: dict[int, MatchRuntime] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                matches = await api_get(client, "/internal/matches/active")
            except Exception as e:
                print(f"api error: {e}")
                await asyncio.sleep(5)
                continue

            for m in matches:
                mid = m["id"]
                if mid in runtimes:
                    continue
                if m["status"] != "provisioning":
                    continue
                port = pool.alloc()
                if port is None:
                    print("no ports available")
                    continue
                full = services.get_match_with_players(mid)
                pa, pb = full["players"][0], full["players"][1]
                proc = spawn_server(
                    mid, port, m["password"], m["rcon_password"], m.get("map_name", "dm/jpntclx")
                )
                await api_post(client, f"/internal/matches/{mid}/port", {"port": port})
                runtimes[mid] = MatchRuntime(
                    match_id=mid,
                    port=port,
                    rcon_password=m["rcon_password"],
                    player_a_id=pa["id"],
                    player_b_id=pb["id"],
                    sof_name_a=pa["sof_name"],
                    sof_name_b=pb["sof_name"],
                    process=proc,
                )
                print(f"spawned match {mid} on {port}")

            finished = []
            for mid, rt in list(runtimes.items()):
                if rt.process.poll() is not None:
                    finished.append((mid, None, "server_exit"))
                    continue
                action = tick_match(rt)
                if not action:
                    # backup: ladder_out json from SoFplus
                    jf = OUT_DIR / f"{mid}.json"
                    if jf.exists():
                        action = f"winner_id:{_winner_from_json(jf, rt)}"
                if action == "dodge":
                    dodger = _dodger(rt)
                    winner = rt.player_b_id if dodger == rt.player_a_id else rt.player_a_id
                    await api_post(
                        client,
                        "/internal/match-result",
                        {"match_id": mid, "winner_id": winner, "dodger_id": dodger, "reason": "dodge"},
                    )
                    finished.append((mid, winner, "dodge"))
                elif action and action.startswith("winner_id:"):
                    wid = int(action.split(":")[1])
                    await api_post(
                        client,
                        "/internal/match-result",
                        {
                            "match_id": mid,
                            "winner_id": wid,
                            "frags": rt.frags,
                            "reason": "completed",
                        },
                    )
                    finished.append((mid, wid, "completed"))

            for mid, _, _ in finished:
                rt = runtimes.pop(mid, None)
                if rt:
                    pool.free(rt.port)
                    if rt.process.poll() is None:
                        rt.process.terminate()
                    jf = OUT_DIR / f"{mid}.json"
                    if jf.exists():
                        jf.unlink(missing_ok=True)

            await asyncio.sleep(4)


def _dodger(rt: MatchRuntime) -> int:
    if rt.sof_name_a.lower() in rt.connected:
        return rt.player_b_id
    if rt.sof_name_b.lower() in rt.connected:
        return rt.player_a_id
    return rt.player_a_id


def _winner_from_json(path: Path, rt: MatchRuntime) -> int:
    import json

    data = json.loads(path.read_text())
    fa = int(data.get("frags_a", data.get("frags_0", 0)))
    fb = int(data.get("frags_b", data.get("frags_1", 0)))
    if fa >= fb:
        return rt.player_a_id
    return rt.player_b_id


def run():
    asyncio.run(run_loop())


if __name__ == "__main__":
    run()
