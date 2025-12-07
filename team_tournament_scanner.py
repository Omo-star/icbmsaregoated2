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
                return ""
            return await r.text()
    except:
        return ""

async def _get_tournament_info(session, tid):
    try:
        async with session.get(f"https://lichess.org/api/tournament/{tid}") as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

async def realtime_team_scanner(interval=30):
    headers = {"User-Agent": "BotLi-RealTimeScanner"}
    async with aiohttp.ClientSession(headers=headers) as session:
        _log("Started real-time team scanner")
        while True:
            if len(SEEN) > 200:
                SEEN.clear()

            html = await _fetch_html(session)
            if not html:
                await asyncio.sleep(interval)
                continue

            ids = re.findall(REGEX, html)
            _log(f"Found {len(ids)} raw IDs: {ids}")

            for tid in ids:
                if tid in SEEN:
                    continue

                _log(f"Processing {tid}")
                info = await _get_tournament_info(session, tid)
                if not info:
                    SEEN.add(tid)
                    continue

                status = info.get("status")
                starts_at = info.get("startsAt")

                now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)

                if status == "started":
                    add_tournament(tid, TEAM)
                    _log(f"JOIN NOW {tid}, tournament already running")
                    SEEN.add(tid)
                    continue

                if starts_at:
                    delta = (int(starts_at) - now_ms) / 1000

                    if delta <= 300:
                        add_tournament(tid, TEAM)
                        _log(f"JOIN NOW {tid}, starts in {int(delta)}s")
                    elif delta < 7200:
                        _log(f"Upcoming {tid}, starts in {int(delta)}s")

                SEEN.add(tid)

            await asyncio.sleep(interval)

team_tournament_loop = realtime_team_scanner

if __name__ == "__main__":
    asyncio.run(realtime_team_scanner())
