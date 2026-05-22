"""In-game ladder commands (ladder_uid), consumed from SoFplus cmd/*.cfg exports."""

from ladder.identity import get_player_by_ladder_uid, is_verified
from ladder import services
from ladder.config import settings


def process_command(action: str, ladder_uid: str, player_name: str = "") -> dict:
    action = (action or "help").strip().lower()
    uid = (ladder_uid or "").strip()
    if action == "help":
        return {
            "ok": True,
            "msg": ".ladder join | leave | status | accept — Discord /link required first",
        }
    if not uid:
        return {"ok": False, "msg": "missing ladder uid (set _sp_cl_info_ladder_uid)"}
    p = get_player_by_ladder_uid(uid)
    if not p and action != "help":
        if action == "status":
            return {"ok": False, "msg": "not linked — use Discord /link"}
        return {"ok": False, "msg": "not linked — complete Discord /link + verify server"}
    try:
        if action == "join":
            if not is_verified(p):
                return {"ok": False, "msg": "not verified — finish /link on verify server"}
            services.join_queue(p["discord_id"])
            n = services.queue_count()
            return {"ok": True, "msg": f"queued ({n} in queue)"}
        if action == "leave":
            services.leave_queue(p["discord_id"])
            return {"ok": True, "msg": "left queue"}
        if action == "accept":
            m = services.accept_match_by_uid(uid)
            if m["status"] == "provisioning":
                return {"ok": True, "msg": "match accepted — server starting, .ladder status for connect"}
            return {"ok": True, "msg": "match accepted — waiting for opponent"}
        if action == "status":
            return {"ok": True, "msg": services.game_status_message(p)}
        return {"ok": False, "msg": "unknown: use join | leave | status | accept"}
    except ValueError as e:
        return {"ok": False, "msg": str(e)}
