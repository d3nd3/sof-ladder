import os
import secrets
import subprocess

from ladder.sof_paths import get_sof_paths
from orchestrator.spawn import _gametype

HUB_PORT = int(os.getenv("LADDER_HUB_PORT", "28907"))


def spawn_hub_server() -> subprocess.Popen:
    """Optional idle lobby (.ladder works on match/verify servers without this)."""
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
        str(HUB_PORT),
        "+set",
        "ladder_matchid",
        "",
        "+set",
        "hostname",
        "SoF Ladder Hub",
        "+set",
        "maxclients",
        "16",
        "+set",
        "public",
        "1",
        "+set",
        "password",
        pw,
        "+set",
        "rcon_password",
        rcon,
        "+map",
        "dm/jpntclx",
        "+exec",
        "ladder_hub.cfg",
    ]
    log = p.log_dir / "hub-server.log"
    return subprocess.Popen(
        args,
        cwd=str(p.cwd),
        env=env,
        stdout=open(log, "w"),
        stderr=subprocess.STDOUT,
    )
