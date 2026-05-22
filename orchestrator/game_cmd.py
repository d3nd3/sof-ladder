"""Poll SoFplus ladder_out/cmd/*.cfg and write cmd_resp/*.cfg."""

from pathlib import Path

from ladder.game_cmd import process_command
from orchestrator.sofplus_io import parse_cfg


def _write_resp(path: Path, ok: bool, msg: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    esc = msg.replace("\\", "\\\\").replace('"', '\\"')
    path.write_text(f'set ok "{"1" if ok else "0"}"\nset ladder_cmd_msg "{esc}"\n')


def poll_game_commands(out_root: Path) -> int:
    cdir = out_root / "cmd"
    if not cdir.is_dir():
        return 0
    n = 0
    for path in list(cdir.glob("*.cfg")):
        data = parse_cfg(path)
        cid = data.get("cmd_id", path.stem)
        action = data.get("action", "")
        uid = data.get("_sp_cl_info_ladder_uid", data.get("ladder_uid", ""))
        name = data.get("_sp_sv_info_client_name", data.get("name", ""))
        result = process_command(action, uid, name)
        _write_resp(out_root / "cmd_resp" / f"{cid}.cfg", result["ok"], result["msg"])
        path.unlink(missing_ok=True)
        n += 1
    return n
