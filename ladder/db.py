import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ladder.config import settings

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = _ROOT / "migrations" / "001_schema.sql"


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
        conn.executescript(_SCHEMA.read_text())
