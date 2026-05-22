from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import os

from ladder.config import settings
from orchestrator.sofplus_io import parse_cfg, tick_sofplus

_CTF_MODE = os.getenv("SOF_DEATHMATCH", "4").strip() == "4"


def _norm(name: str) -> str:
    return name.strip().lower()


@dataclass
class MatchRuntime:
    match_id: int
    port: int
    rcon_password: str
    player_a_id: int
    player_b_id: int
    ladder_uid_a: str
    ladder_uid_b: str
    sof_name_a: str
    sof_name_b: str
    process: object
    out_root: Path
    started_at: datetime = field(default_factory=datetime.utcnow)
    both_connected_at: datetime | None = None
    frags: dict[int, int] = field(default_factory=dict)
    connected_uids: set[str] = field(default_factory=set)


def _uids_from_check_exports(out_root: Path, uid_a: str, uid_b: str) -> set[str]:
    """Uids seen via ladder_check.func (verify/ev_*.cfg or presence/<uid>.cfg)."""
    want = {u for u in (uid_a, uid_b) if u}
    found: set[str] = set()
    for sub, pattern in (("verify", "ev_*.cfg"), ("presence", "*.cfg")):
        d = out_root / sub
        if not d.is_dir():
            continue
        for path in d.glob(pattern):
            uid = (parse_cfg(path).get("_sp_cl_info_ladder_uid") or "").strip()
            if uid in want:
                found.add(uid)
    return found


def tick_match_sofplus(rt: MatchRuntime) -> str | None:
    expect = {_norm(rt.sof_name_a), _norm(rt.sof_name_b)} - {"", "?"}
    action, frags, both_at, _ = tick_sofplus(
        rt.out_root,
        rt.match_id,
        rt.sof_name_a,
        rt.sof_name_b,
        rt.player_a_id,
        rt.player_b_id,
        rt.started_at,
        rt.both_connected_at,
        expect,
    )
    uid_set = _uids_from_check_exports(rt.out_root, rt.ladder_uid_a, rt.ladder_uid_b)
    rt.connected_uids = uid_set
    rt.frags = {**frags, **rt.frags}
    if rt.ladder_uid_a in uid_set and rt.ladder_uid_b in uid_set:
        rt.both_connected_at = rt.both_connected_at or datetime.utcnow()
    elif action and len(uid_set) < 2:
        return action
    if not rt.both_connected_at and datetime.utcnow() - rt.started_at > timedelta(minutes=5):
        return "dodge"
    if rt.both_connected_at:
        if not _CTF_MODE:
            fa, fb = rt.frags.get(rt.player_a_id, 0), rt.frags.get(rt.player_b_id, 0)
            if fa >= settings.fraglimit:
                return f"winner_id:{rt.player_a_id}"
            if fb >= settings.fraglimit:
                return f"winner_id:{rt.player_b_id}"
        if len(uid_set) < 2 and datetime.utcnow() - rt.both_connected_at > timedelta(seconds=30):
            if rt.ladder_uid_a in uid_set:
                return f"winner_id:{rt.player_a_id}"
            if rt.ladder_uid_b in uid_set:
                return f"winner_id:{rt.player_b_id}"
    result_path = rt.out_root / str(rt.match_id) / "result.cfg"
    if not action and result_path.is_file():
        return _sofplus_result(rt)
    return action


def _sofplus_result(rt: MatchRuntime) -> str | None:
    from orchestrator.sofplus_io import read_result, resolve_winner_id

    res = read_result(rt.out_root, rt.match_id)
    if not res or not res.ready:
        return None
    wid = resolve_winner_id(
        res.winner_name, rt.frags, rt.sof_name_a, rt.sof_name_b, rt.player_a_id, rt.player_b_id
    )
    if wid is not None:
        return f"winner_id:{wid}"
    if rt.ladder_uid_a in rt.connected_uids and rt.ladder_uid_b not in rt.connected_uids:
        return f"winner_id:{rt.player_a_id}"
    if rt.ladder_uid_b in rt.connected_uids and rt.ladder_uid_a not in rt.connected_uids:
        return f"winner_id:{rt.player_b_id}"
    return None


def tick_match(rt: MatchRuntime) -> str | None:
    return tick_match_sofplus(rt)
