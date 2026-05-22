import secrets
from pathlib import Path

from ladder import identity
from ladder.sof_paths import get_sof_paths
from orchestrator.spawn import build_launch_cmd
from orchestrator.sofplus_io import parse_cfg

VERIFY_PORT = int(__import__("os").getenv("VERIFY_SERVER_PORT", "28908"))


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
    pw = secrets.token_hex(4)
    rcon = secrets.token_hex(8)
    args, env = build_launch_cmd(0, VERIFY_PORT, pw, rcon, "dm/jpntclx")
    import subprocess

    p = get_sof_paths()
    log = p.log_dir / "verify-server.log"
    proc = subprocess.Popen(
        args,
        cwd=str(p.cwd),
        env=env,
        stdout=open(log, "w"),
        stderr=subprocess.STDOUT,
    )
    return proc, rcon
