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
                _log(f"HTTP {r.status}")
                return ""
            return await r.text()
    except Exception as e:
        _log(f"Error {e}")
        return ""

async def _get_tournament_info(session, tid):
    api = f"https://lichess.org/api/tournament/{tid}"
    try:
        async with session.get(api) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

async def realtime_team_scanner(interval=15):
    headers = {"User-Agent": "BotLi-RealTimeScanner"}
    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            html = await _fetch_html(session)
            if not html:
                await asyncio.sleep(interval)
                continue

            ids = re.findall(REGEX, html)
            for tid in ids:
                if tid in SEEN:
                    continue

                info = await _get_tournament_info(session, tid)
                if not info:
                    continue

                start = info.get("startsAt")
                if not start:
                    SEEN.add(tid)
                    continue

                start_ms = int(start)
                now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
                delta = (start_ms - now_ms) / 1000

                if delta <= 300:
                    add_tournament(tid, TEAM)
                    _log(f"JOIN NOW {tid}, starts in {int(delta)}s")
                else:
                    _log(f"Seen {tid}, starts in {int(delta)}s")

                SEEN.add(tid)

            await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(realtime_team_scanner())
