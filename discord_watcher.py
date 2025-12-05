import os
import re
import discord
from discord.ext import commands
from tournament_queue import add_tournament

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
WATCH_GUILD_ID = 1151481550282690631
WATCH_CHANNEL_IDS = [
    1416719630541787209,
    1151495957859545109,
]

TOURNAMENT_REGEX = r"lichess\.org/tournament/([A-Za-z0-9]{8})"


class TournamentWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.guild is None:
            return
        if WATCH_GUILD_ID and message.guild.id != WATCH_GUILD_ID:
            return
        if message.channel.id not in WATCH_CHANNEL_IDS:
            return
        matches = re.findall(TOURNAMENT_REGEX, message.content)
        for tid in matches:
            add_tournament(tid)


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"[DiscordWatcher] Logged in as {bot.user}")

    bot.add_cog(TournamentWatcher(bot))
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
