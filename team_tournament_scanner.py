import re
import asyncio
import aiohttp
import datetime
from bs4 import BeautifulSoup

TEAM = "darkonbot"
SEEN = set()

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RTTeamScanner {ts}] {msg}")

async def fetch_team_tournaments_html(session):
    url = f"https://lichess.org/team/{TEAM}/tournaments/upcoming"

    try:
        async with session.get(url, headers={"User-Agent": "BotLi-HTMLScraper"}) as r:
            if r.status != 200:
                _log(f"HTTP {r.status} scraping tournaments")
                text = await r.text()
                _log(f"Body preview: {text[:200].replace(chr(10), ' ')}")
                return []

            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")

            tournaments = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.match(r"^/tournament/([a-zA-Z0-9]{8,12})$", href)
                if m:
                    tid = m.group(1)
                    tournaments.append(tid)

            tournaments = list(set(tournaments))
            return tournaments

    except Exception as e:
        _log(f"Error scraping tournaments: {e}")
        return []
