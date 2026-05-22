import os
import asyncio

VERIFY_SERVER_PORT = int(os.getenv("VERIFY_SERVER_PORT", "28908"))
LADDER_HUB_PORT = int(os.getenv("LADDER_HUB_PORT", "28907"))

import discord
from discord import app_commands
from discord.ext import commands

from ladder.config import settings  # loads .env from project root
from bot.api_client import ApiClient

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or 0)
LADDER_CHANNEL_ID = int(os.getenv("DISCORD_LADDER_CHANNEL_ID", "0") or 0)

api = ApiClient()
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)


def _provisional(games: int) -> str:
    return " (provisional)" if games < 10 else ""


class LadderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Find 1v1", style=discord.ButtonStyle.green, custom_id="ladder_find")
    async def find(self, interaction: discord.Interaction, _):
        try:
            p = await api.queue_join(str(interaction.user.id))
            await interaction.response.send_message(
                f"Queued as **{p.get('sof_name', '?')}** (Elo {p['elo']}). Queue size updating in channel.",
                ephemeral=True,
            )
            await refresh_ladder_embed(interaction.client)
            if p.get("state") == "match_offer" and p.get("active_match_id"):
                m = await api.get_match(p["active_match_id"])
                await notify_match_offer(interaction.client, m)
        except RuntimeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @discord.ui.button(label="Leave queue", style=discord.ButtonStyle.secondary, custom_id="ladder_leave")
    async def leave(self, interaction: discord.Interaction, _):
        try:
            await api.queue_leave(str(interaction.user.id))
            await interaction.response.send_message("Left queue.", ephemeral=True)
            await refresh_ladder_embed(interaction.client)
        except RuntimeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.primary, custom_id="ladder_stats")
    async def stats(self, interaction: discord.Interaction, _):
        try:
            p = await api.get_player(str(interaction.user.id))
            msg = (
                f"**{p.get('sof_name') or 'unverified'}** (uid `{p.get('ladder_uid') or '—'}`)\n"
                f"Elo: **{p['elo']}**{_provisional(p['games_played'])}\n"
                f"Games: {p['games_played']} | State: `{p['state']}`"
            )
            if p.get("cooldown_until"):
                msg += f"\nCooldown until: {p['cooldown_until']} UTC"
            await interaction.response.send_message(msg, ephemeral=True)
        except RuntimeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)


class AcceptView(discord.ui.View):
    def __init__(self, match_id: int):
        super().__init__(timeout=settings.match_offer_seconds)
        self.match_id = match_id

    @discord.ui.button(label="Accept match", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, _):
        try:
            m = await api.accept(self.match_id, str(interaction.user.id))
            await interaction.response.send_message(
                f"Accepted match #{self.match_id}. Status: `{m['status']}`",
                ephemeral=True,
            )
            if m["status"] == "provisioning":
                await notify_match_ready(interaction.client, self.match_id)
        except RuntimeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)


async def refresh_ladder_embed(client: discord.Client):
    if not LADDER_CHANNEL_ID:
        return
    ch = client.get_channel(LADDER_CHANNEL_ID)
    if not ch:
        return
    qc = await api.queue_count()
    embed = discord.Embed(
        title="SoF 1v1 Ladder",
        description="Use `/link` first — set `_sp_cl_info_*` cvars and join the verify server.",
        color=0xC41E3A,
    )
    embed.add_field(name="In queue", value=str(qc["count"]), inline=True)
    embed.add_field(name="Map", value="dm/jpntclx", inline=True)
    embed.add_field(name="Frag limit", value=str(settings.fraglimit), inline=True)
    view = LadderView()
    async for msg in ch.history(limit=10):
        if msg.author.id == client.user.id and msg.embeds:
            await msg.edit(embed=embed, view=view)
            return
    await ch.send(embed=embed, view=view)


async def notify_match_offer(client: discord.Client, match: dict):
    mid = match["id"]
    for p in match.get("players", []):
        user = await client.fetch_user(int(p["discord_id"]))
        other = next(x for x in match["players"] if x["discord_id"] != p["discord_id"])
        embed = discord.Embed(
            title=f"Match #{mid} found",
            description=f"Opponent: **{other.get('sof_name', '?')}** (Elo {other['elo']})",
            color=0xFFD700,
        )
        embed.add_field(name="Accept within", value=f"{settings.match_offer_seconds}s", inline=False)
        try:
            await user.send(embed=embed, view=AcceptView(mid))
        except discord.Forbidden:
            ch = client.get_channel(LADDER_CHANNEL_ID)
            if ch:
                await ch.send(f"<@{p['discord_id']}> enable DMs for match offers.")


async def notify_match_ready(client: discord.Client, match_id: int):
    m = await api.get_match(match_id)
    ip = settings.server_connect_ip
    port = m.get("port") or "TBD"
    for p in m.get("players", []):
        user = await client.fetch_user(int(p["discord_id"]))
        embed = discord.Embed(title=f"Match #{match_id} — connect now", color=0x00AA00)
        embed.add_field(name="Server", value=f"`{ip}:{port}`", inline=False)
        embed.add_field(name="Password", value=f"`{m.get('password', '')}`", inline=True)
        embed.add_field(name="Map", value=m.get("map_name", "dm/jpntclx"), inline=True)
        embed.add_field(name="Match ID", value=str(match_id), inline=True)
        embed.add_field(
            name="Console",
            value=f"`connect {ip}:{port}` then enter password when prompted.",
            inline=False,
        )
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass


async def sync_app_commands():
    """Guild sync is instant; requires the bot to be in that server with applications.commands."""
    guild = discord.utils.get(bot.guilds, id=GUILD_ID) if GUILD_ID else None
    try:
        if guild:
            bot.tree.copy_global_to(guild=guild)
            cmds = await bot.tree.sync(guild=guild)
            print(f"Synced {len(cmds)} command(s) to guild '{guild.name}' ({guild.id})")
            return
        if GUILD_ID:
            print(
                f"WARNING: Bot is not in DISCORD_GUILD_ID={GUILD_ID}. "
                "Invite it with scopes bot + applications.commands (see README). "
                "Using global sync instead (~1 hour to propagate)."
            )
        cmds = await bot.tree.sync()
        print(f"Synced {len(cmds)} command(s) globally")
    except discord.Forbidden:
        print(
            "WARNING: Missing Access for guild command sync. "
            "Re-invite the bot with applications.commands, or fix DISCORD_GUILD_ID."
        )
        cmds = await bot.tree.sync()
        print(f"Synced {len(cmds)} command(s) globally as fallback")


@bot.event
async def on_ready():
    bot.add_view(LadderView())
    app_id = bot.application_id
    if app_id and GUILD_ID:
        print(
            "Invite (if needed): "
            f"https://discord.com/oauth2/authorize?client_id={app_id}"
            "&permissions=2147486720&scope=bot%20applications.commands"
        )
    await sync_app_commands()
    await refresh_ladder_embed(bot)
    bot.loop.create_task(poll_pending_offers())


async def poll_pending_offers():
    await bot.wait_until_ready()
    offered: set[int] = set()
    connected: set[int] = set()
    while not bot.is_closed():
        try:
            for m in await api.pending_matches():
                if m["id"] not in offered:
                    offered.add(m["id"])
                    await notify_match_offer(bot, m)
            for m in await api.live_matches():
                if m["id"] not in connected:
                    connected.add(m["id"])
                    await notify_match_ready(bot, m["id"])
            for mid in list(offered):
                m = await api.get_match(mid)
                if m["status"] != "pending_accept":
                    offered.discard(mid)
        except Exception:
            pass
        await asyncio.sleep(5)


@bot.tree.command(name="link", description="Verify your SoF client (SoFplus sp_sv_client_check)")
async def cmd_link(interaction: discord.Interaction):
    try:
        p = await api.link_start(str(interaction.user.id))
        ip = settings.server_connect_ip
        vport = VERIFY_SERVER_PORT
        hub = LADDER_HUB_PORT
        embed = discord.Embed(
            title="Link your SoF client",
            description=(
                "Add these to your **game shortcut** or `autoexec.cfg` "
                "(`_sp_cl_info_*` cvars are read by the server via SoFplus `sp_sv_client_check`):"
            ),
            color=0x3498DB,
        )
        embed.add_field(
            name="Launch cvars",
            value=f"```\n{p['launch_cvars']}\n```",
            inline=False,
        )
        embed.add_field(
            name="Verify",
            value=(
                f"1. Start SoF with those cvars\n"
                f"2. Connect to **`{ip}:{vport}`** (verify server, ~{p['verify_ttl_minutes']} min window)\n"
                f"3. When verified, `/stats` shows linked — then queue\n"
                f"4. In-game: **`.ladder join`** on any ladder server (match, verify"
                + (f", or hub `{ip}:{hub}`" if os.getenv("LADDER_HUB_ENABLED", "").lower() in ("1", "true", "yes") else "")
                + ")"
            ),
            inline=False,
        )
        embed.set_footer(text="ladder_uid is assigned by the ladder; do not share it.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except RuntimeError as e:
        await interaction.response.send_message(str(e), ephemeral=True)


@bot.tree.command(name="stats", description="Your ladder stats")
async def cmd_stats(interaction: discord.Interaction):
    try:
        p = await api.get_player(str(interaction.user.id))
        msg = (
            f"**{p.get('sof_name') or 'not linked'}** — Elo **{p['elo']}**{_provisional(p['games_played'])}, "
            f"{p['games_played']} games, state `{p['state']}`"
        )
        if p.get("ladder_uid") and not p.get("verify_nonce"):
            msg += f"\nShortcut: `+set _sp_cl_info_ladder_uid \"{p['ladder_uid']}\"`"
        elif p.get("ladder_uid"):
            msg += f"\nuid `{p['ladder_uid']}` (finish /link verify first)"
        await interaction.response.send_message(msg, ephemeral=True)
    except RuntimeError as e:
        await interaction.response.send_message(str(e), ephemeral=True)


@bot.tree.command(name="leaderboard", description="Top ladder players")
async def cmd_leaderboard(interaction: discord.Interaction):
    try:
        rows = await api.leaderboard()
        lines = [f"**{i+1}.** {r['sof_name']} — {r['elo']} ({r['games_played']}g)" for i, r in enumerate(rows)]
        await interaction.response.send_message("\n".join(lines) or "No players yet.", ephemeral=True)
    except RuntimeError as e:
        await interaction.response.send_message(str(e), ephemeral=True)


@bot.tree.command(name="cancel", description="Leave matchmaking queue")
async def cmd_cancel(interaction: discord.Interaction):
    try:
        await api.queue_leave(str(interaction.user.id))
        await interaction.response.send_message("Left queue.", ephemeral=True)
        await refresh_ladder_embed(bot)
    except RuntimeError as e:
        await interaction.response.send_message(str(e), ephemeral=True)


# Hook: API should notify bot on new offers — bot polls DB via new endpoint
@bot.tree.command(name="accept", description="Accept a pending match offer")
@app_commands.describe(match_id="Match ID from DM")
async def cmd_accept(interaction: discord.Interaction, match_id: int):
    try:
        m = await api.accept(match_id, str(interaction.user.id))
        await interaction.response.send_message(f"Match #{match_id} status: `{m['status']}`", ephemeral=True)
        if m["status"] == "provisioning":
            await notify_match_ready(bot, match_id)
    except RuntimeError as e:
        await interaction.response.send_message(str(e), ephemeral=True)


def run():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN required")
    bot.run(token)


if __name__ == "__main__":
    run()
