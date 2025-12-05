import os
import json
import re
import asyncio
import discord
from discord.ext import commands
from typing import List

TOURNAMENT_FILE = "tournaments.json"

DISCORD_TOKEN = os.getenv("DISCORD_KEY")

WATCH_CHANNELS = [
    1151495957859545109,  
    1416719630541787209
]

TOURNAMENT_REGEX = r"lichess\.org/tournament/([A-Za-z0-9]{8})"


def load_tournaments() -> List[str]:
    if not os.path.exists(TOURNAMENT_FILE):
        return []
    try:
        with open(TOURNAMENT_FILE, "r") as f:
            data = json.load(f)
            return data.get("pending", [])
    except Exception:
        return []


def save_tournament(tid: str):
    data = {"pending": []}

    if os.path.exists(TOURNAMENT_FILE):
        with open(TOURNAMENT_FILE, "r") as f:
            data = json.load(f)

    if "pending" not in data:
        data["pending"] = []

    if tid not in data["pending"]:
        data["pending"].append(tid)
        with open(TOURNAMENT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[DiscordWatcher] Added new tournament ID: {tid}")
    else:
        print(f"[DiscordWatcher] Tournament {tid} already present.")


class TournamentWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id not in WATCH_CHANNELS:
            return

        matches = re.findall(TOURNAMENT_REGEX, message.content)
        if matches:
            for tid in matches:
                save_tournament(tid)


def run_discord_watcher():
    intents = discord.Intents.default()
    intents.message_content = True 

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"Bot ready for action! Logged in as {bot.user}")

    bot.add_cog(TournamentWatcher(bot))
    
    bot.run(DISCORD_TOKEN)
