import asyncio
import aiohttp
import datetime
import re
from tournament_queue import add_tournament

TEAM = "darkonbot"
URL = f"https://lichess.org/team/{TEAM}"
REGEX = r"lichess\.org/tournament/([A-Za-z0-9]{8})"
SEEN = set()

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RTTeamScanner {ts}] {msg}")

async def _fetch_html(session):
    try:
        async with session.get(URL) as r:
            if r.status != 200:
                _log(f"Team page HTTP {r.status}")
                return ""
            return await r.text()
    except Exception as e:
        _log(f"Fetch error: {e}")
        return ""

async def _get_tournament_info(session, tid):
    try:
        async with session.get(f"https://lichess.org/api/tournament/{tid}") as r:
            if r.status != 200:
                _log(f"API error {r.status} for {tid}")
                return None
            return await r.json()
    except Exception as e:
        _log(f"API exception for {tid}: {e}")
        return None

async def realtime_team_scanner(interval=30):
    _log("Started real-time team scanner")
    headers = {"User-Agent": "BotLi-RealTimeScanner"}

    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            if len(SEEN) > 200:
                SEEN.clear()

            html = await _fetch_html(session)
            if not html:
                _log("No HTML or error fetching team page")
                await asyncio.sleep(interval)
                continue

            ids = re.findall(REGEX, html)
            _log(f"Found {len(ids)} tournaments on page")

            for tid in ids:
                if tid in SEEN:
                    continue

                _log(f"Processing {tid}")

                info = await _get_tournament_info(session, tid)
                if not info:
                    _log(f"Skipping {tid}, API returned nothing")
                    SEEN.add(tid)
                    continue

                start = info.get("startsAt")
                _log(f"Tournament {tid} startsAt={start}")

                if not start:
                    SEEN.add(tid)
                    continue

                now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
                delta = (int(start) - now_ms) / 1000

                if delta <= 300:
                    add_tournament(tid, TEAM)
                    _log(f"JOIN NOW {tid}, starts in {int(delta)}s")
                else:
                    _log(f"{tid} starts in {int(delta)}s")

                SEEN.add(tid)

            await asyncio.sleep(interval)

team_tournament_loop = realtime_team_scanner
