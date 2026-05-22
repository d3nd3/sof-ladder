from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from ladder.config import settings
from ladder.db import init_db
from ladder import services

app = FastAPI(title="SoF Ladder API", version="1.0.0")


def verify_bot(authorization: str | None = Header(None)):
    if authorization != f"Bearer {settings.bot_api_secret}":
        raise HTTPException(401, "unauthorized")


def verify_orch(x_orchestrator_secret: str | None = Header(None)):
    if x_orchestrator_secret != settings.orchestrator_secret:
        raise HTTPException(401, "unauthorized")


class LinkStartBody(BaseModel):
    discord_id: str


class DiscordBody(BaseModel):
    discord_id: str


class AcceptBody(BaseModel):
    discord_id: str


class MatchResultBody(BaseModel):
    match_id: int
    winner_id: int | None = None
    frags: dict[int, int] = {}
    reason: str = "completed"
    dodger_id: int | None = None


class AssignPortBody(BaseModel):
    port: int


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/players/link/start", dependencies=[Depends(verify_bot)])
def link_start(body: LinkStartBody):
    try:
        return services.link_start(body.discord_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/players/{discord_id}", dependencies=[Depends(verify_bot)])
def get_player(discord_id: str):
    p = services.get_player(discord_id)
    if not p:
        raise HTTPException(404, "not found")
    return p


@app.get("/players/{discord_id}/pending", dependencies=[Depends(verify_bot)])
def pending(discord_id: str):
    return services.pending_offers_for_discord(discord_id)


@app.post("/queue/join", dependencies=[Depends(verify_bot)])
def queue_join(body: DiscordBody):
    try:
        return services.join_queue(body.discord_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/queue/leave", dependencies=[Depends(verify_bot)])
def queue_leave(body: DiscordBody):
    try:
        return services.leave_queue(body.discord_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/queue/count", dependencies=[Depends(verify_bot)])
def queue_count():
    return {"count": services.queue_count()}


@app.get("/matches/pending", dependencies=[Depends(verify_bot)])
def pending_matches():
    return [m for m in services.list_pending_offers() if m]


@app.get("/matches/live", dependencies=[Depends(verify_bot)])
def live_matches():
    return [m for m in services.list_live_matches() if m]


@app.post("/matches/{match_id}/accept", dependencies=[Depends(verify_bot)])
def accept_match(match_id: int, body: AcceptBody):
    try:
        return services.accept_match(body.discord_id, match_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/matches/{match_id}", dependencies=[Depends(verify_bot)])
def get_match(match_id: int):
    m = services.get_match_with_players(match_id)
    if not m:
        raise HTTPException(404, "not found")
    return m


@app.get("/leaderboard", dependencies=[Depends(verify_bot)])
def leaderboard(limit: int = 20):
    return services.leaderboard(limit)


@app.get("/internal/matches/active", dependencies=[Depends(verify_orch)])
def active_matches():
    return services.list_provisioning_matches()


@app.post("/internal/matches/{match_id}/port", dependencies=[Depends(verify_orch)])
def assign_port(match_id: int, body: AssignPortBody):
    return services.assign_match_port(match_id, body.port)


@app.post("/internal/match-result", dependencies=[Depends(verify_orch)])
def match_result(body: MatchResultBody):
    try:
        if body.dodger_id and body.winner_id:
            services.apply_dodge_penalty(body.match_id, body.dodger_id, body.winner_id)
            return services.get_match(body.match_id)
        return services.finish_match(
            body.match_id, body.winner_id, body.frags, body.reason
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


def run():
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    run()
