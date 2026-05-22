import asyncio
import shutil
from pathlib import Path

import httpx

from ladder.config import settings
from ladder.db import init_db
from ladder.sof_paths import get_sof_paths
from ladder import services
from orchestrator.monitor import MatchRuntime, tick_match
from orchestrator.spawn import spawn_server
from ladder import identity
from orchestrator.sofplus_io import match_dir, read_result
from orchestrator.verify import VERIFY_PORT, poll_verify_exports, spawn_verify_server
from orchestrator.game_cmd import poll_game_commands

API = settings.api_base.rstrip("/")
ORCH_HEADERS = {"X-Orchestrator-Secret": settings.orchestrator_secret}


def _out_root() -> Path:
    return get_sof_paths().ladder_out


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


def _cleanup_match_files(mid: int, out_root: Path):
    d = match_dir(out_root, mid)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)


def _dodger(rt: MatchRuntime) -> int | None:
    if rt.ladder_uid_a in rt.connected_uids:
        return rt.player_b_id
    if rt.ladder_uid_b in rt.connected_uids:
        return rt.player_a_id
    return None


def _cleanup_presence_uids(out_root: Path, *uids: str):
    pres = out_root / "presence"
    if not pres.is_dir():
        return
    for uid in uids:
        if uid:
            (pres / f"{uid}.cfg").unlink(missing_ok=True)


def _finish_match(
    client: httpx.AsyncClient,
    mid: int,
    *,
    winner_id: int | None,
    frags: dict | None = None,
    dodger_id: int | None = None,
    reason: str,
):
    body: dict = {"match_id": mid, "winner_id": winner_id, "reason": reason}
    if frags:
        body["frags"] = frags
    if dodger_id is not None and winner_id is not None:
        body["dodger_id"] = dodger_id
    return api_post(client, "/internal/match-result", body)


async def _handle_dodge_or_noshow(client: httpx.AsyncClient, mid: int, rt: MatchRuntime):
    dodger = _dodger(rt)
    if dodger is None:
        await _finish_match(client, mid, winner_id=None, reason="no_show")
        return
    winner = rt.player_b_id if dodger == rt.player_a_id else rt.player_a_id
    await _finish_match(
        client,
        mid,
        winner_id=winner,
        dodger_id=dodger,
        reason="dodge",
    )


async def run_loop():
    init_db()
    out_root = _out_root()
    out_root.mkdir(parents=True, exist_ok=True)
    sp = get_sof_paths()
    print(f"SoF install: {sp.install_dir} | user: {sp.user_subfolder} -> {sp.user_dir}")
    print(f"addons: {sp.addons_dir} | ladder_out: {out_root}")
    n_abandon = services.reconcile_orchestrator_startup()
    if n_abandon:
        print(f"reconciled {n_abandon} orphaned match(es) from prior run")
    pool = PortPool()
    pool.used = services.reserved_match_ports()
    if pool.used:
        print(f"reserved ports: {sorted(pool.used)}")
    runtimes: dict[int, MatchRuntime] = {}
    orphan = out_root / "0"
    if orphan.is_dir():
        shutil.rmtree(orphan, ignore_errors=True)
    verify_proc = None
    verify_rcon = ""
    hub_proc = None
    if settings.ladder_hub_enabled:
        from orchestrator.hub import HUB_PORT, spawn_hub_server

        hub_proc = spawn_hub_server()
        print(f"optional hub on {HUB_PORT}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            poll_game_commands(out_root)
            if hub_proc is not None and hub_proc.poll() is not None:
                from orchestrator.hub import spawn_hub_server

                hub_proc = spawn_hub_server()
                print("hub server restarted")
            pending = identity.list_pending_verifications()
            if pending:
                if verify_proc is None or verify_proc.poll() is not None:
                    verify_proc, verify_rcon = spawn_verify_server()
                    print(f"verify server on {VERIFY_PORT}")
                poll_verify_exports(out_root)
            elif verify_proc is not None and verify_proc.poll() is None:
                verify_proc.terminate()
                verify_proc = None

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
                _cleanup_match_files(mid, out_root)
                proc = spawn_server(
                    mid,
                    port,
                    m["password"],
                    m["rcon_password"],
                    m.get("map_name", "dm/jpntclx"),
                    pa.get("ladder_uid") or "",
                    pb.get("ladder_uid") or "",
                )
                await api_post(client, f"/internal/matches/{mid}/port", {"port": port})
                runtimes[mid] = MatchRuntime(
                    match_id=mid,
                    port=port,
                    rcon_password=m["rcon_password"],
                    player_a_id=pa["id"],
                    player_b_id=pb["id"],
                    ladder_uid_a=pa["ladder_uid"] or "",
                    ladder_uid_b=pb["ladder_uid"] or "",
                    sof_name_a=pa.get("sof_name") or "?",
                    sof_name_b=pb.get("sof_name") or "?",
                    process=proc,
                    out_root=out_root,
                )
                print(f"spawned match {mid} on {port} (SoFplus export -> {match_dir(out_root, mid)})")

            finished = []
            for mid, rt in list(runtimes.items()):
                if rt.process.poll() is not None:
                    action = tick_match(rt)
                    if action and action.startswith("winner_id:"):
                        wid = int(action.split(":")[1])
                        await _finish_match(
                            client,
                            mid,
                            winner_id=wid,
                            frags=rt.frags,
                            reason="completed (server_exit)",
                        )
                        finished.append(mid)
                    elif action == "dodge" or not rt.both_connected_at:
                        await _handle_dodge_or_noshow(client, mid, rt)
                        finished.append(mid)
                    continue

                action = tick_match(rt)
                if action == "dodge":
                    await _handle_dodge_or_noshow(client, mid, rt)
                    finished.append(mid)
                elif action and action.startswith("winner_id:"):
                    wid = int(action.split(":")[1])
                    res = read_result(out_root, mid)
                    reason = f"completed ({res.end_reason if res else 'sofplus'})"
                    await _finish_match(
                        client,
                        mid,
                        winner_id=wid,
                        frags=rt.frags,
                        reason=reason,
                    )
                    finished.append(mid)

            for mid in finished:
                rt = runtimes.pop(mid, None)
                if rt:
                    pool.free(rt.port)
                    if rt.process.poll() is None:
                        rt.process.terminate()
                    _cleanup_match_files(mid, out_root)
                    _cleanup_presence_uids(out_root, rt.ladder_uid_a, rt.ladder_uid_b)

            await asyncio.sleep(4)


def run():
    asyncio.run(run_loop())


if __name__ == "__main__":
    run()
