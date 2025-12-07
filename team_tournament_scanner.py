import asyncio
import aiohttp
import datetime
import re
from bs4 import BeautifulSoup
from tournament_queue import add_tournament

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
                text = await r.text()
                _log(f"HTTP {r.status} scraping tournaments")
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

            return list(set(tournaments))

    except Exception as e:
        _log(f"Error scraping tournaments: {e}")
        return []

async def realtime_team_scanner(_, interval=30):
    _log("Started real-time team scanner")

    async with aiohttp.ClientSession() as session:
        while True:
            if len(SEEN) > 500:
                SEEN.clear()

            tournaments = await fetch_team_tournaments_html(session)

            if not tournaments:
                _log("No tournaments found on HTML page")
                await asyncio.sleep(interval)
                continue

            _log(f"Found {len(tournaments)} tournaments in HTML")

            for tid in tournaments:
                if tid in SEEN:
                    continue

                add_tournament(tid, TEAM)
                _log(f"JOIN NOW {tid}")

                SEEN.add(tid)

            await asyncio.sleep(interval)

async def team_tournament_loop(token):
    await realtime_team_scanner(token, interval=30)
