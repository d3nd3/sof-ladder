import os
import subprocess
from pathlib import Path

from ladder.config import settings

_ROOT = Path(__file__).resolve().parents[1]
_GAME = _ROOT / "game"


def build_launch_cmd(match_id: int, port: int, password: str, rcon_password: str, map_name: str) -> list[str]:
    sof_exe = os.getenv("SOF_EXE", "/opt/sof/sofmp.exe")
    wine = os.getenv("WINE", "wine")
    xvfb = os.getenv("XVFB_RUN", "xvfb-run")
    prefix = os.getenv("WINEPREFIX", "/opt/sof/wineprefix")
    cfg = _GAME / "ladder_match.cfg"
    env = {**os.environ, "WINEPREFIX": prefix}
    args = [
        xvfb,
        "-a",
        wine,
        sof_exe,
        "+set",
        "dedicated",
        "1",
        "+set",
        "user",
        "user",
        "+set",
        "console",
        "1",
        "+set",
        "hostport",
        str(port),
        "+set",
        "ladder_matchid",
        str(match_id),
        "+set",
        "password",
        password,
        "+set",
        "rcon_password",
        rcon_password,
        "+set",
        "maxclients",
        "2",
        "+set",
        "fraglimit",
        str(settings.fraglimit),
        "+set",
        "timelimit",
        "15",
        "+set",
        "deathmatch",
        "1",
        "+map",
        map_name,
        "+exec",
        str(cfg.name),
    ]
    return args, env


def spawn_server(match_id: int, port: int, password: str, rcon_password: str, map_name: str) -> subprocess.Popen:
    log_dir = Path(os.getenv("SOF_LADDER_LOG_DIR", "/var/log/sof-ladder")) / str(match_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    args, env = build_launch_cmd(match_id, port, password, rcon_password, map_name)
    log = open(log_dir / "server.log", "w")
    return subprocess.Popen(
        args,
        cwd=str(Path(os.getenv("SOF_CWD", "/opt/sof"))),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
