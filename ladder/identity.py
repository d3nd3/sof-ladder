"""Discord ↔ in-game identity via SoFplus sp_sv_client_check + _sp_cl_info_* cvars."""

import secrets
import uuid
from datetime import datetime, timedelta

from ladder import states
from ladder.db import get_db

_LINK_BLOCKED = {states.QUEUED, states.MATCH_OFFER, states.IN_MATCH}

VERIFY_TTL_MINUTES = 15
# Readable by sp_sv_client_check (must use _sp_cl_info_ prefix)
CVAR_UID = "_sp_cl_info_ladder_uid"
CVAR_VERIFY = "_sp_cl_info_ladder_verify"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _expires(minutes: int) -> str:
    return (datetime.utcnow() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def is_verified(player: dict) -> bool:
    return bool(player.get("ladder_uid")) and not player.get("verify_nonce")


def start_link(discord_id: str) -> dict:
    """Issue ladder_uid + verify nonce; client sets _sp_cl_info_* cvars (no userinfo flag)."""
    uid = str(uuid.uuid4())
    nonce = secrets.token_hex(16)
    exp = _expires(VERIFY_TTL_MINUTES)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if row and row["state"] in _LINK_BLOCKED:
            raise ValueError(
                "leave queue or finish your match before re-linking (/link rotates your uid)"
            )
        if row:
            conn.execute(
                """UPDATE players SET ladder_uid=?, verify_nonce=?, verify_expires=?,
                   linked_at=NULL, sof_name=NULL, updated_at=? WHERE discord_id=?""",
                (uid, nonce, exp, _now(), discord_id),
            )
        else:
            conn.execute(
                """INSERT INTO players (discord_id, ladder_uid, verify_nonce, verify_expires, state)
                   VALUES (?, ?, ?, ?, 'idle')""",
                (discord_id, uid, nonce, exp),
            )
        p = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
    p = dict(p)
    p["launch_cvars"] = (
        f'+set {CVAR_UID} "{uid}" +set {CVAR_VERIFY} "{nonce}"'
    )
    p["verify_ttl_minutes"] = VERIFY_TTL_MINUTES
    return p


def list_pending_verifications() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM players WHERE verify_nonce IS NOT NULL
               AND verify_expires > datetime('now')""",
        ).fetchall()
        return [dict(r) for r in rows]


def try_confirm_from_check(
    ladder_uid: str,
    verify_nonce: str,
    in_game_name: str,
    slot: int,
) -> dict | None:
    """Match sp_sv_client_check results to a pending Discord link."""
    if not ladder_uid or not verify_nonce:
        return None
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM players WHERE ladder_uid=? AND verify_nonce=?
               AND verify_expires > datetime('now')""",
            (ladder_uid.strip(), verify_nonce.strip()),
        ).fetchone()
        if not row:
            return None
        name = in_game_name.strip() or None
        conn.execute(
            """UPDATE players SET verify_nonce=NULL, verify_expires=NULL,
               linked_at=?, sof_name=?, updated_at=? WHERE id=?""",
            (_now(), name, _now(), row["id"]),
        )
        out = conn.execute("SELECT * FROM players WHERE id=?", (row["id"],)).fetchone()
        return dict(out)


# alias for older call sites
try_confirm_from_userinfo = try_confirm_from_check


def get_player_by_ladder_uid(ladder_uid: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE ladder_uid=? AND verify_nonce IS NULL",
            (ladder_uid.strip(),),
        ).fetchone()
        return dict(row) if row else None
