import os
import re
import discord
from discord.ext import commands
from tournament_queue import add_tournament

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

WATCH_GUILD_IDS = [
    1151481550282690631,    
    1440020962295676938,    
]

WATCH_CHANNEL_IDS = [
    1416719630541787209,     
    1151495957859545109,     
    1446656767999344701,      
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

        if message.guild.id not in WATCH_GUILD_IDS:
            return

        if message.channel.id not in WATCH_CHANNEL_IDS:
            return

        matches = re.findall(TOURNAMENT_REGEX, message.content)

        for tid in matches:
            add_tournament(tid)
            print(f"[DiscordWatcher] Tournament detected in {message.guild.name} → {tid}")


class DiscordBot(commands.Bot):
    async def setup_hook(self):
        await self.add_cog(TournamentWatcher(self))

    async def on_ready(self):
        print(f"[DiscordWatcher] Logged in as {self.user}")


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN")

    intents = discord.Intents.default()
    intents.message_content = True

    bot = DiscordBot(command_prefix="!", intents=intents)
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
