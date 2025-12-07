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

def parse_time_text(text):
    text = text.strip()

    if text.lower() == "playing right now":
        return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

    m = re.match(r"in (\d+) hours?", text)
    if m:
        hours = int(m.group(1))
        return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=hours)

    try:
        dt = datetime.datetime.strptime(text, "%b %d, %Y, %I:%M %p")
        return dt.replace(tzinfo=datetime.timezone.utc)
    except:
        return None

async def fetch_team_tournaments_html(session):
    url = f"https://lichess.org/team/{TEAM}/tournaments"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html",
    }

    try:
        async with session.get(url, headers=headers) as r:
            if r.status != 200:
                text = await r.text()
                _log(f"HTTP {r.status} scraping tournaments")
                _log(f"Body preview: {text[:200].replace(chr(10), ' ')}")
                return []

            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")

            container = soup.find("div", class_="team-tournaments__next")
            if not container:
                return []

            rows = container.find_all("tr", class_=lambda c: c and "enterable" in c)

            upcoming = []

            for row in rows:
                link = row.find("a", href=True)
                if not link:
                    continue

                href = link["href"]
                m = re.match(r"^/tournament/([A-Za-z0-9]{8,12})$", href)
                if not m:
                    continue

                tid = m.group(1)

                time_cell = row.find("td", string=True)
                if not time_cell:
                    continue

                start_time = parse_time_text(time_cell.text)
                if not start_time:
                    continue

                now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
                delta = (start_time - now).total_seconds()

                if delta <= 0 or delta <= 300:
                    upcoming.append(tid)

            return upcoming

    except Exception as e:
        _log(f"Error scraping tournaments: {e}")
        return []

async def realtime_team_scanner(_, interval=30):
    _log("Started real-time team scanner")

    async with aiohttp.ClientSession() as session:
        while True:
            if len(SEEN) > 300:
                SEEN.clear()

            tournaments = await fetch_team_tournaments_html(session)

            if not tournaments:
                _log("No tournaments within join window")
                await asyncio.sleep(interval)
                continue

            _log(f"Joinable tournaments: {tournaments}")

            for tid in tournaments:
                if tid in SEEN:
                    continue

                add_tournament(tid, TEAM)
                _log(f"JOIN NOW {tid}")

                SEEN.add(tid)

            await asyncio.sleep(interval)

async def team_tournament_loop(token):
    await realtime_team_scanner(token, interval=30)
