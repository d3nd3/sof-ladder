import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ladder.config import settings

_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS = sorted((_ROOT / "migrations").glob("*.sql"))


def _db_path() -> str:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        p = url.replace("sqlite:///", "", 1)
        return str(_ROOT / p) if not p.startswith("/") else p
    return str(_ROOT / "sof_ladder.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        for path in _MIGRATIONS:
            try:
                conn.executescript(path.read_text())
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
