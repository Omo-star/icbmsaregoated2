import asyncio
import aiohttp
import datetime
import re
from bs4 import BeautifulSoup
from tournament_queue import add_tournament

TEAM = "darkonbot"
SEEN = set()
JOIN_WINDOW_SECONDS = 300

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RTTeamScanner {ts}] {msg}")

def parse_time_from_infos_cell(info_td):
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

    time_tag = info_td.find("time")
    if time_tag and time_tag.has_attr("datetime"):
        try:
            iso = time_tag["datetime"].replace("Z", "+00:00")
            return datetime.datetime.fromisoformat(iso)
        except:
            pass

    lines = [l.strip() for l in info_td.text.split("\n") if l.strip()]
    if len(lines) < 2:
        return None

    t = lines[1].lower()

    if t == "playing right now":
        return now

    m = re.match(r"in (\d+) minutes?", t)
    if m:
        return now + datetime.timedelta(minutes=int(m.group(1)))

    m = re.match(r"in (\d+) hours?", t)
    if m:
        return now + datetime.timedelta(hours=int(m.group(1)))

    try:
        dt = datetime.datetime.strptime(lines[1], "%b %d, %Y, %I:%M %p")
        return dt.replace(tzinfo=datetime.timezone.utc)
    except:
        return None

async def fetch_team_tournaments_html(session):
    url = f"https://lichess.org/team/{TEAM}/tournaments"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}

    try:
        async with session.get(url, headers=headers) as r:
            if r.status != 200:
                _log(f"HTTP {r.status} scraping tournaments")
                return []

            soup = BeautifulSoup(await r.text(), "html.parser")
            container = soup.find("div", class_="team-tournaments__next")
            if not container:
                return []

            rows = container.find_all("tr", class_=lambda c: c and "enterable" in c)
            now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            found = []

            for row in rows:
                link = row.find("a", href=True)
                if not link:
                    continue

                m = re.match(r"^/tournament/([A-Za-z0-9]{8,12})$", link["href"])
                if not m:
                    continue

                tid = m.group(1)

                info_td = row.find("td", class_="infos")
                if not info_td:
                    continue

                start_time = parse_time_from_infos_cell(info_td)
                if not start_time:
                    continue

                delta = (start_time - now).total_seconds()
                if delta <= JOIN_WINDOW_SECONDS:
                    found.append(tid)

            return found

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
