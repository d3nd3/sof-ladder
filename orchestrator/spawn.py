import os
import subprocess

from ladder.config import settings
from ladder.sof_paths import get_sof_paths


def _gametype() -> str:
    return os.getenv("SOF_DEATHMATCH", "4").strip() or "4"


def build_launch_cmd(match_id: int, port: int, password: str, rcon_password: str, map_name: str) -> tuple[list[str], dict]:
    p = get_sof_paths()
    wine = os.getenv("WINE", "wine")
    xvfb = os.getenv("XVFB_RUN", "xvfb-run")
    gt = _gametype()
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
        gt,
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
        "timelimit",
        "15",
    ]
    if gt == "4":
        args += ["+set", "ctf_loops", os.getenv("CTF_LOOPS", "10"), "+set", "fraglimit", "0"]
    else:
        args += ["+set", "fraglimit", str(settings.fraglimit)]
    args += [
        "+map",
        map_name,
        "+exec",
        "ladder_match.cfg",
    ]
    return args, env


def spawn_server(match_id: int, port: int, password: str, rcon_password: str, map_name: str) -> subprocess.Popen:
    p = get_sof_paths()
    log_dir = p.log_dir / str(match_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    args, env = build_launch_cmd(match_id, port, password, rcon_password, map_name)
    log = open(log_dir / "server.log", "w")
    return subprocess.Popen(
        args,
        cwd=str(p.cwd),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
