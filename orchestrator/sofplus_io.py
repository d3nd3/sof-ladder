"""Read ladder match data written by SoFplus sp_sc_cvar_save (set key \"value\" lines)."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ladder.config import settings


def match_dir(out_root: Path, match_id: int) -> Path:
    return out_root / str(match_id)


def parse_cfg(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("set "):
            continue
        rest = line[4:].strip()
        if not rest:
            continue
        m = re.match(r'^(\S+)\s+"(.*)"\s*$', rest)
        if m:
            data[m.group(1)] = m.group(2)
            continue
        parts = rest.split(None, 1)
        if len(parts) == 2:
            data[parts[0]] = parts[1].strip().strip('"')
    return data


def _norm(name: str) -> str:
    return name.strip().lower()


@dataclass
class SofplusSnapshot:
    connected_names: set[str]
    frags_by_name: dict[str, int]


def read_snapshots(out_root: Path, match_id: int) -> SofplusSnapshot:
    d = match_dir(out_root, match_id)
    names: set[str] = set()
    frags: dict[str, int] = {}
    if not d.is_dir():
        return SofplusSnapshot(names, frags)
    for p in sorted(d.glob("tmp_player_*.cfg")):
        cvars = parse_cfg(p)
        ip = cvars.get("_sp_sv_info_client_ip", "")
        name = cvars.get("_sp_sv_info_client_name", "")
        if not ip or not name:
            continue
        n = _norm(name)
        names.add(n)
        try:
            frags[n] = int(cvars.get("_sp_sv_info_client_frags", "0"))
        except ValueError:
            frags[n] = 0
    return SofplusSnapshot(names, frags)


@dataclass
class SofplusResult:
    ready: bool
    match_id: str
    end_reason: str
    winner_name: str
    winner_frags: int
    player_count: int
    raw: dict[str, str]


def read_result(out_root: Path, match_id: int) -> SofplusResult | None:
    path = match_dir(out_root, match_id) / "result.cfg"
    if not path.is_file():
        return None
    raw = parse_cfg(path)
    if raw.get("ladder_ready") != "1":
        return None
    try:
        wf = int(raw.get("ladder_winner_frags", "0"))
    except ValueError:
        wf = 0
    try:
        pc = int(raw.get("ladder_player_count", "0"))
    except ValueError:
        pc = 0
    return SofplusResult(
        ready=True,
        match_id=raw.get("ladder_matchid", str(match_id)),
        end_reason=raw.get("ladder_end_reason", "unknown"),
        winner_name=raw.get("ladder_winner_name", ""),
        winner_frags=wf,
        player_count=pc,
        raw=raw,
    )


def resolve_winner_id(
    winner_name: str,
    frags: dict[str, int],
    sof_name_a: str,
    sof_name_b: str,
    player_a_id: int,
    player_b_id: int,
) -> int | None:
    wn = _norm(winner_name)
    if wn == _norm(sof_name_a):
        return player_a_id
    if wn == _norm(sof_name_b):
        return player_b_id
    fa = frags.get(player_a_id, frags.get(_norm(sof_name_a), 0))
    fb = frags.get(player_b_id, frags.get(_norm(sof_name_b), 0))
    if fa > fb:
        return player_a_id
    if fb > fa:
        return player_b_id
    return None


def frags_for_players(
    snap: SofplusSnapshot,
    sof_name_a: str,
    sof_name_b: str,
    player_a_id: int,
    player_b_id: int,
) -> dict[int, int]:
    out: dict[int, int] = {}
    na, nb = _norm(sof_name_a), _norm(sof_name_b)
    if na in snap.frags_by_name:
        out[player_a_id] = snap.frags_by_name[na]
    if nb in snap.frags_by_name:
        out[player_b_id] = snap.frags_by_name[nb]
    return out


def tick_sofplus(
    out_root: Path,
    match_id: int,
    sof_name_a: str,
    sof_name_b: str,
    player_a_id: int,
    player_b_id: int,
    started_at: datetime,
    both_connected_at: datetime | None,
    expect: set[str],
) -> tuple[str | None, dict[int, int], datetime | None, set[str]]:
    """
    Primary match monitor via SoFplus files under ladder_out/<match_id>/.
    Returns (action, frags, both_connected_at, connected_names).
    action: None | dodge | winner_id:N
    """
    snap = read_snapshots(out_root, match_id)
    connected = snap.connected_names & expect
    frags = frags_for_players(snap, sof_name_a, sof_name_b, player_a_id, player_b_id)
    both_at = both_connected_at
    if len(connected) >= 2 and not both_at:
        both_at = datetime.utcnow()

    result = read_result(out_root, match_id)
    if result and result.ready:
        wid = resolve_winner_id(
            result.winner_name,
            frags,
            sof_name_a,
            sof_name_b,
            player_a_id,
            player_b_id,
        )
        if wid is not None:
            return f"winner_id:{wid}", frags, both_at, connected

    if not both_at and datetime.utcnow() - started_at > timedelta(minutes=5):
        return "dodge", frags, both_at, connected

    if both_at:
        fa = frags.get(player_a_id, 0)
        fb = frags.get(player_b_id, 0)
        if fa >= settings.fraglimit:
            return f"winner_id:{player_a_id}", frags, both_at, connected
        if fb >= settings.fraglimit:
            return f"winner_id:{player_b_id}", frags, both_at, connected
        if len(connected) < 2 and datetime.utcnow() - both_at > timedelta(seconds=30):
            if _norm(sof_name_a) in connected:
                return f"winner_id:{player_a_id}", frags, both_at, connected
            if _norm(sof_name_b) in connected:
                return f"winner_id:{player_b_id}", frags, both_at, connected

    return None, frags, both_at, connected
