import os
import secrets
import subprocess
from pathlib import Path

from ladder import identity
from ladder.sof_paths import get_sof_paths
from orchestrator.sofplus_io import parse_cfg
from orchestrator.spawn import _gametype

VERIFY_PORT = int(os.getenv("VERIFY_SERVER_PORT", "28908"))


def _ingest_verify_file(path: Path) -> bool:
    data = parse_cfg(path)
    uid = data.get("_sp_cl_info_ladder_uid", data.get("ladder_uid", ""))
    nonce = data.get("_sp_cl_info_ladder_verify", data.get("ladder_verify", ""))
    name = data.get("_sp_sv_info_client_name", data.get("name", ""))
    slot = int(data.get("slot", "0") or 0)
    if identity.try_confirm_from_check(uid, nonce, name, slot):
        path.unlink(missing_ok=True)
        return True
    return False


def poll_verify_exports(out_root: Path) -> int:
    """Ingest SoFplus ladder_check.func output under ladder_out/verify/."""
    vdir = out_root / "verify"
    if not vdir.is_dir():
        return 0
    n = 0
    for path in list(vdir.glob("ev_*.cfg")):
        if _ingest_verify_file(path):
            n += 1
    return n


def spawn_verify_server() -> tuple[object, str]:
    """Verify-only server (no ladder_matchid — avoids ladder_out/0/ pollution)."""
    p = get_sof_paths()
    wine = os.getenv("WINE", "wine")
    xvfb = os.getenv("XVFB_RUN", "xvfb-run")
    pw = secrets.token_hex(4)
    rcon = secrets.token_hex(8)
    env = {**os.environ, "WINEPREFIX": str(p.wineprefix)}
    args = [
        xvfb,
        "-a",
        wine,
        str(p.exe),
        "+set",
        "user",
        p.user_subfolder,
        "+set",
        "dedicated",
        "1",
        "+set",
        "deathmatch",
        _gametype(),
        "+set",
        "console",
        "1",
        "+set",
        "hostport",
        str(VERIFY_PORT),
        "+set",
        "ladder_matchid",
        "",
        "+set",
        "hostname",
        "SoF Ladder Verify",
        "+set",
        "password",
        pw,
        "+set",
        "rcon_password",
        rcon,
        "+map",
        "dm/jpntclx",
        "+exec",
        "ladder_verify.cfg",
    ]
    log = p.log_dir / "verify-server.log"
    proc = subprocess.Popen(
        args,
        cwd=str(p.cwd),
        env=env,
        stdout=open(log, "w"),
        stderr=subprocess.STDOUT,
    )
    return proc, rcon
