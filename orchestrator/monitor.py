import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ladder.config import settings
from orchestrator.rcon import QuakeRcon


@dataclass
class MatchRuntime:
    match_id: int
    port: int
    rcon_password: str
    player_a_id: int
    player_b_id: int
    sof_name_a: str
    sof_name_b: str
    process: object
    started_at: datetime = field(default_factory=datetime.utcnow)
    both_connected_at: datetime | None = None
    frags: dict[int, int] = field(default_factory=dict)
    connected: set[str] = field(default_factory=set)


def _norm(name: str) -> str:
    return name.strip().lower()


def parse_sofplus_frags(rcon: QuakeRcon, slots: int = 8) -> dict[str, int]:
    frags = {}
    for slot in range(slots):
        try:
            rcon.command(f"sp_sv_info_client {slot}")
            out = rcon.command("echo $_sp_sv_info_client_name")
        except Exception:
            continue
        # read cvar via rcon is awkward; parse status as fallback
    out = rcon.command("status")
    for line in out.splitlines():
        m = re.search(r"^\s*(\d+)\s+(\S+)\s+(\d+)", line)
        if m:
            frags[_norm(m.group(2))] = int(m.group(3))
    return frags


def tick_match(rt: MatchRuntime) -> str | None:
    """Returns action: None, 'dodge', 'forfeit', 'finished', or 'winner_id:<id>'."""
    rcon = QuakeRcon("127.0.0.1", rt.port, rt.rcon_password)
    try:
        status = rcon.command("status")
    except Exception:
        if datetime.utcnow() - rt.started_at > timedelta(minutes=5):
            return "dodge"
        return None

    names = set()
    for line in status.splitlines():
        m = re.search(r"^\s*(\d+)\s+(\S+)\s+(\d+)", line)
        if m:
            n = _norm(m.group(2))
            names.add(n)
            sc = int(m.group(3))
            if _norm(rt.sof_name_a) == n:
                rt.frags[rt.player_a_id] = sc
            if _norm(rt.sof_name_b) == n:
                rt.frags[rt.player_b_id] = sc

    expected = {_norm(rt.sof_name_a), _norm(rt.sof_name_b)}
    rt.connected = names & expected
    if len(rt.connected) >= 2 and not rt.both_connected_at:
        rt.both_connected_at = datetime.utcnow()

    if not rt.both_connected_at and datetime.utcnow() - rt.started_at > timedelta(minutes=5):
        return "dodge"

    if rt.both_connected_at:
        fa = rt.frags.get(rt.player_a_id, 0)
        fb = rt.frags.get(rt.player_b_id, 0)
        if fa >= settings.fraglimit:
            return f"winner_id:{rt.player_a_id}"
        if fb >= settings.fraglimit:
            return f"winner_id:{rt.player_b_id}"
        # forfeit: one disconnected
        if len(rt.connected) < 2 and datetime.utcnow() - rt.both_connected_at > timedelta(seconds=30):
            if _norm(rt.sof_name_a) in rt.connected:
                return f"winner_id:{rt.player_a_id}"
            if _norm(rt.sof_name_b) in rt.connected:
                return f"winner_id:{rt.player_b_id}"

    if "intermission" in status.lower() or "scoreboard" in status.lower():
        fa = rt.frags.get(rt.player_a_id, 0)
        fb = rt.frags.get(rt.player_b_id, 0)
        if fa > fb:
            return f"winner_id:{rt.player_a_id}"
        if fb > fa:
            return f"winner_id:{rt.player_b_id}"
    return None
