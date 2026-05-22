import secrets
from datetime import datetime, timedelta

from ladder import states
from ladder.config import settings
from ladder.db import get_db
from ladder.elo import apply_elo
from ladder import penalties


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _iso_after(seconds: int) -> str:
    return (datetime.utcnow() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def get_or_create_player(discord_id: str) -> dict:
    with get_db() as conn:
        penalties.clear_expired_cooldowns(conn)
        row = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO players (discord_id, state) VALUES (?, ?)",
            (discord_id, states.IDLE),
        )
        row = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        return dict(row)


def link_player(discord_id: str, sof_name: str) -> dict:
    name = sof_name.strip()
    if not name:
        raise ValueError("sof_name required")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM players WHERE LOWER(sof_name)=LOWER(?) AND discord_id!=?",
            (name, discord_id),
        ).fetchone()
        if existing:
            raise ValueError("sof_name already linked")
        get_or_create_player(discord_id)
        conn.execute(
            "UPDATE players SET sof_name=?, updated_at=? WHERE discord_id=?",
            (name, _now(), discord_id),
        )
        row = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        return dict(row)


def get_player(discord_id: str) -> dict | None:
    with get_db() as conn:
        penalties.clear_expired_cooldowns(conn)
        row = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        return dict(row) if row else None


def queue_count() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM queue_entries").fetchone()["c"]


def join_queue(discord_id: str) -> dict:
    p = get_or_create_player(discord_id)
    if not p.get("sof_name"):
        raise ValueError("link sof_name first")
    with get_db() as conn:
        penalties.clear_expired_cooldowns(conn)
        p = dict(conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone())
        if p["state"] == states.SUSPENDED:
            raise ValueError("account suspended")
        if p["state"] == states.COOLDOWN and p["cooldown_until"]:
            if p["cooldown_until"] > _now():
                raise ValueError(f"cooldown until {p['cooldown_until']}")
        if p["state"] not in states.QUEUEABLE:
            raise ValueError(f"cannot queue in state {p['state']}")
        if penalties.check_spam_queue(conn, p["id"]):
            penalties.apply_cooldown(conn, p["id"], 5, "spam_queue")
            raise ValueError("queue spam cooldown 5 min")
        conn.execute(
            "INSERT OR REPLACE INTO queue_entries (player_id, enqueued_at, elo_at_queue) VALUES (?, ?, ?)",
            (p["id"], _now(), p["elo"]),
        )
        conn.execute(
            "INSERT INTO queue_join_log (player_id) VALUES (?)",
            (p["id"],),
        )
        conn.execute(
            "UPDATE players SET state=?, updated_at=? WHERE id=?",
            (states.QUEUED, _now(), p["id"]),
        )
        try_pair_queue(conn)
        row = conn.execute("SELECT * FROM players WHERE id=?", (p["id"],)).fetchone()
        return dict(row)


def leave_queue(discord_id: str) -> dict:
    with get_db() as conn:
        p = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if not p:
            raise ValueError("player not found")
        conn.execute("DELETE FROM queue_entries WHERE player_id=?", (p["id"],))
        if p["state"] == states.QUEUED:
            conn.execute(
                "UPDATE players SET state=?, updated_at=? WHERE id=?",
                (states.IDLE, _now(), p["id"]),
            )
        row = conn.execute("SELECT * FROM players WHERE id=?", (p["id"],)).fetchone()
        return dict(row)


def _elo_window_seconds(enqueued_at: str) -> int:
    try:
        t0 = datetime.strptime(enqueued_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return settings.elo_window_start
    waited = (datetime.utcnow() - t0).total_seconds()
    extra = int(waited // settings.elo_window_interval) * settings.elo_window_grow
    return min(settings.elo_window_start + extra, settings.elo_window_cap)


def try_pair_queue(conn) -> int | None:
    rows = conn.execute(
        """SELECT q.*, p.discord_id, p.sof_name, p.elo, p.games_played
           FROM queue_entries q JOIN players p ON p.id = q.player_id
           ORDER BY q.enqueued_at"""
    ).fetchall()
    if len(rows) < 2:
        return None
    best = None
    for i, a in enumerate(rows):
        wa = _elo_window_seconds(a["enqueued_at"])
        for b in rows[i + 1 :]:
            wb = _elo_window_seconds(b["enqueued_at"])
            w = max(wa, wb)
            if abs(a["elo"] - b["elo"]) <= w:
                diff = abs(a["elo"] - b["elo"])
                if best is None or diff < best[0]:
                    best = (diff, a, b)
    if not best:
        return None
    _, a, b = best
    return create_match_offer(conn, a["player_id"], b["player_id"])


def create_match_offer(conn, pid_a: int, pid_b: int) -> int:
    deadline = _iso_after(settings.match_offer_seconds)
    pw = secrets.token_hex(4)
    rcon = secrets.token_hex(8)
    cur = conn.execute(
        """INSERT INTO matches (status, password, rcon_password, player_a_id, player_b_id, accept_deadline)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (states.MATCH_PENDING, pw, rcon, pid_a, pid_b, deadline),
    )
    mid = cur.lastrowid
    for pid in (pid_a, pid_b):
        conn.execute("DELETE FROM queue_entries WHERE player_id=?", (pid,))
        conn.execute(
            "UPDATE players SET state=?, active_match_id=?, updated_at=? WHERE id=?",
            (states.MATCH_OFFER, mid, _now(), pid),
        )
    return mid


def accept_match(discord_id: str, match_id: int) -> dict:
    with get_db() as conn:
        p = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if not p:
            raise ValueError("player not found")
        m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m or m["status"] != states.MATCH_PENDING:
            raise ValueError("invalid match")
        if p["id"] not in (m["player_a_id"], m["player_b_id"]):
            raise ValueError("not in match")
        if m["accept_deadline"] and m["accept_deadline"] < _now():
            cancel_match_offer(conn, match_id, "accept_timeout")
            raise ValueError("match offer expired")
        key = f"accept_{p['id']}"
        # track accepts via match_players placeholder
        conn.execute(
            """INSERT OR IGNORE INTO match_players (match_id, player_id) VALUES (?, ?)""",
            (match_id, p["id"]),
        )
        conn.execute(
            "UPDATE match_players SET connected_at=? WHERE match_id=? AND player_id=?",
            (_now(), match_id, p["id"]),
        )
        ac = conn.execute(
            "SELECT COUNT(*) AS c FROM match_players WHERE match_id=? AND connected_at IS NOT NULL",
            (match_id,),
        ).fetchone()["c"]
        if ac >= 2:
            conn.execute(
                "UPDATE matches SET status=? WHERE id=?",
                (states.MATCH_PROVISIONING, match_id),
            )
            for pid in (m["player_a_id"], m["player_b_id"]):
                conn.execute(
                    "UPDATE players SET state=?, updated_at=? WHERE id=?",
                    (states.IN_MATCH, _now(), pid),
                )
        row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        return dict(row)


def cancel_match_offer(conn, match_id: int, reason: str):
    m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not m:
        return
    conn.execute(
        "UPDATE matches SET status=?, finished_at=? WHERE id=?",
        (states.MATCH_CANCELLED, _now(), match_id),
    )
    for pid in (m["player_a_id"], m["player_b_id"]):
        penalties.add_strike(conn, pid, reason, match_id)
        penalties.apply_cooldown(conn, pid, 3, reason, match_id)
        conn.execute(
            "UPDATE players SET state=?, active_match_id=NULL, updated_at=? WHERE id=?",
            (states.COOLDOWN, _now(), pid),
        )


def expire_stale_offers(conn):
    rows = conn.execute(
        """SELECT id FROM matches WHERE status=? AND accept_deadline < datetime('now')""",
        (states.MATCH_PENDING,),
    ).fetchall()
    for r in rows:
        cancel_match_offer(conn, r["id"], "accept_timeout")


def prune_stale_queue(conn):
    conn.execute(
        """DELETE FROM queue_entries WHERE enqueued_at < datetime('now', ?)""",
        (f"-{settings.queue_max_minutes} minutes",),
    )
    conn.execute(
        """UPDATE players SET state=?, updated_at=?
           WHERE state=? AND id NOT IN (SELECT player_id FROM queue_entries)""",
        (states.IDLE, _now(), states.QUEUED),
    )


def get_match(match_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        return dict(row) if row else None


def get_match_with_players(match_id: int) -> dict | None:
    with get_db() as conn:
        m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m:
            return None
        out = dict(m)
        out["players"] = []
        for key, label in (("player_a_id", "a"), ("player_b_id", "b")):
            p = conn.execute("SELECT * FROM players WHERE id=?", (m[key],)).fetchone()
            if p:
                out["players"].append({**dict(p), "side": label})
        return out


def list_provisioning_matches() -> list[dict]:
    with get_db() as conn:
        expire_stale_offers(conn)
        prune_stale_queue(conn)
        try_pair_queue(conn)
        rows = conn.execute(
            "SELECT * FROM matches WHERE status IN (?, ?)",
            (states.MATCH_PROVISIONING, states.MATCH_LIVE),
        ).fetchall()
        return [dict(r) for r in rows]


def assign_match_port(match_id: int, port: int) -> dict:
    with get_db() as conn:
        conn.execute(
            "UPDATE matches SET port=?, status=?, server_started_at=? WHERE id=?",
            (port, states.MATCH_LIVE, _now(), match_id),
        )
        row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        return dict(row)


def finish_match(
    match_id: int,
    winner_id: int | None,
    frags: dict[int, int],
    reason: str = "completed",
) -> dict:
    with get_db() as conn:
        m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if not m or m["status"] in (states.MATCH_FINISHED, states.MATCH_CANCELLED):
            raise ValueError("invalid match")
        pa = conn.execute("SELECT * FROM players WHERE id=?", (m["player_a_id"],)).fetchone()
        pb = conn.execute("SELECT * FROM players WHERE id=?", (m["player_b_id"],)).fetchone()
        ra, rb = pa["elo"], pb["elo"]
        ga, gb = pa["games_played"], pb["games_played"]
        if winner_id == pa["id"]:
            score_a = 1.0
        elif winner_id == pb["id"]:
            score_a = 0.0
        else:
            score_a = 0.5
        na, nb, da, db, ka, kb = apply_elo(ra, rb, score_a, ga, gb)
        conn.execute(
            "UPDATE matches SET status=?, winner_id=?, finished_at=? WHERE id=?",
            (states.MATCH_FINISHED, winner_id, _now(), match_id),
        )
        for pid, before, after, delta, k in (
            (pa["id"], ra, na, da, ka),
            (pb["id"], rb, nb, db, kb),
        ):
            conn.execute(
                """INSERT OR REPLACE INTO match_players
                   (match_id, player_id, rating_before, rating_after, delta, k_used, frags)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (match_id, pid, before, after, delta, k, frags.get(pid, 0)),
            )
            conn.execute(
                """UPDATE players SET elo=?, games_played=games_played+1,
                   state=?, active_match_id=NULL, updated_at=? WHERE id=?""",
                (after, states.IDLE, _now(), pid),
            )
        row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        return dict(row)


def apply_dodge_penalty(match_id: int, dodger_id: int, winner_id: int):
    with get_db() as conn:
        penalties.add_strike(conn, dodger_id, "dodge", match_id)
        penalties.apply_cooldown(conn, dodger_id, 15, "dodge", match_id)
        conn.execute(
            "UPDATE players SET elo=MAX(100, elo-25), updated_at=? WHERE id=?",
            (_now(), dodger_id),
        )
    with get_db() as conn:
        m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        pa = conn.execute("SELECT * FROM players WHERE id=?", (m["player_a_id"])).fetchone()
        pb = conn.execute("SELECT * FROM players WHERE id=?", (m["player_b_id"])).fetchone()
        winner = pa if winner_id == pa["id"] else pb
        loser = pb if winner_id == pa["id"] else pa
        ra, rb = winner["elo"], loser["elo"]
        ga, gb = winner["games_played"], loser["games_played"]
        na, nb, da, db, ka, kb = apply_elo(ra, rb, 1.0, ga, gb)
        conn.execute(
            "UPDATE matches SET status=?, winner_id=?, finished_at=? WHERE id=?",
            (states.MATCH_FINISHED, winner_id, _now(), match_id),
        )
        for pid, before, after, delta, k in (
            (winner["id"], ra, na, da, ka),
            (loser["id"], loser["elo"], loser["elo"], 0, 0),
        ):
            conn.execute(
                """INSERT OR REPLACE INTO match_players
                   (match_id, player_id, rating_before, rating_after, delta, k_used, frags)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (match_id, pid, before, after, delta, k),
            )
        conn.execute(
            """UPDATE players SET elo=?, games_played=games_played+1,
               state=?, active_match_id=NULL, updated_at=? WHERE id=?""",
            (na, states.IDLE, _now(), winner["id"]),
        )
        conn.execute(
            """UPDATE players SET games_played=games_played+1,
               state=?, active_match_id=NULL, updated_at=? WHERE id=?""",
            (states.IDLE, _now(), loser["id"]),
        )


def leaderboard(limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT discord_id, sof_name, elo, games_played FROM players
               WHERE sof_name IS NOT NULL ORDER BY elo DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_live_matches() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM matches WHERE status=? AND port IS NOT NULL",
            (states.MATCH_LIVE,),
        ).fetchall()
        return [get_match_with_players(r["id"]) for r in rows]


def list_pending_offers() -> list[dict]:
    with get_db() as conn:
        expire_stale_offers(conn)
        rows = conn.execute(
            "SELECT id FROM matches WHERE status=?",
            (states.MATCH_PENDING,),
        ).fetchall()
        return [get_match_with_players(r["id"]) for r in rows]


def pending_offers_for_discord(discord_id: str) -> list[dict]:
    with get_db() as conn:
        p = conn.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if not p or not p["active_match_id"]:
            return []
        m = get_match_with_players(p["active_match_id"])
        return [m] if m and m["status"] == states.MATCH_PENDING else []
