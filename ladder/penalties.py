from datetime import datetime, timedelta

from ladder import states
from ladder.db import get_db


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _iso_after(minutes: int) -> str:
    return (datetime.utcnow() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def log_penalty(conn, player_id: int, reason: str, penalty_type: str, match_id: int | None = None):
    conn.execute(
        "INSERT INTO penalty_events (player_id, reason, penalty_type, match_id) VALUES (?, ?, ?, ?)",
        (player_id, reason, penalty_type, match_id),
    )


def apply_cooldown(conn, player_id: int, minutes: int, reason: str, match_id: int | None = None):
    until = _iso_after(minutes)
    conn.execute(
        "UPDATE players SET state=?, cooldown_until=?, updated_at=? WHERE id=?",
        (states.COOLDOWN, until, _now(), player_id),
    )
    log_penalty(conn, player_id, reason, f"cooldown_{minutes}m", match_id)


def add_strike(conn, player_id: int, reason: str, match_id: int | None = None) -> int:
    conn.execute(
        "UPDATE players SET strikes = strikes + 1, updated_at=? WHERE id=?",
        (_now(), player_id),
    )
    log_penalty(conn, player_id, reason, "strike", match_id)
    row = conn.execute("SELECT strikes FROM players WHERE id=?", (player_id,)).fetchone()
    strikes = row["strikes"]
    if strikes >= 3:
        apply_cooldown(conn, player_id, 24 * 60, "three_strikes_24h", match_id)
        conn.execute(
            "UPDATE players SET state=?, updated_at=? WHERE id=?",
            (states.SUSPENDED, _now(), player_id),
        )
        log_penalty(conn, player_id, "three_strikes", "suspend_24h", match_id)
    return strikes


def check_spam_queue(conn, player_id: int) -> bool:
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM queue_join_log
           WHERE player_id=? AND created_at > datetime('now', '-10 minutes')""",
        (player_id,),
    ).fetchone()
    return row["c"] >= 5


def clear_expired_cooldowns(conn):
    conn.execute(
        """UPDATE players SET state=?, cooldown_until=NULL, updated_at=?
           WHERE state IN (?, ?) AND cooldown_until IS NOT NULL
           AND cooldown_until <= datetime('now')""",
        (states.IDLE, _now(), states.COOLDOWN, states.SUSPENDED),
    )
