"""Resolve SoF install paths from SOF_INSTALL_DIR with optional overrides."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class SofPaths:
    install_dir: Path
    exe: Path
    cwd: Path
    user_subfolder: str
    user_dir: Path
    addons_dir: Path
    wineprefix: Path
    ladder_out: Path
    log_dir: Path


def _path(env_key: str, default: Path) -> Path:
    raw = os.getenv(env_key, "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


@lru_cache(maxsize=1)
def get_sof_paths() -> SofPaths:
    """
    SOF_INSTALL_DIR — game root (exe, wineprefix, user subfolder as child of cwd).

    SOF_USER_SUBFOLDER — value for +set user (e.g. user, ladder). Data lives at
    $SOF_CWD/$SOF_USER_SUBFOLDER/; ladder scripts in .../sofplus/addons/.

    Optional overrides: SOF_EXE, SOF_CWD, SOF_USER_DIR, WINEPREFIX,
    SOF_LADDER_OUT_DIR, SOF_LADDER_LOG_DIR.
    """
    install = _path("SOF_INSTALL_DIR", Path("/opt/sof"))
    cwd = _path("SOF_CWD", install)
    sub = os.getenv("SOF_USER_SUBFOLDER", "user").strip() or "user"
    user = _path("SOF_USER_DIR", cwd / sub)
    return SofPaths(
        install_dir=install,
        exe=_path("SOF_EXE", install / "sofmp.exe"),
        cwd=cwd,
        user_subfolder=sub,
        user_dir=user,
        addons_dir=user / "sofplus" / "addons",
        wineprefix=_path("WINEPREFIX", install / "wineprefix"),
        ladder_out=_path("SOF_LADDER_OUT_DIR", user / "sofplus" / "data" / "ladder_out"),
        log_dir=_path("SOF_LADDER_LOG_DIR", Path("/var/log/sof-ladder")),
    )


if __name__ == "__main__":
    get_sof_paths.cache_clear()
    p = get_sof_paths()
    for name in (
        "install_dir",
        "exe",
        "cwd",
        "user_subfolder",
        "user_dir",
        "addons_dir",
        "wineprefix",
        "ladder_out",
        "log_dir",
    ):
        print(f"{name}: {getattr(p, name)}")
