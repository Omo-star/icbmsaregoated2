import asyncio
import aiohttp
import datetime
import re
from tournament_queue import add_tournament

TEAM = "darkonbot"
URL = f"https://lichess.org/team/{TEAM}"

REGEX = r'href="(?:https://lichess\.org)?/tournament/([A-Za-z0-9]{8})'

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
    try:
        async with session.get(f"https://lichess.org/api/tournament/{tid}") as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None


async def realtime_team_scanner(interval=20):
    _log("Started real-time team scanner")

    headers = {"User-Agent": "BotLi-RealTimeScanner"}

    async with aiohttp.ClientSession(headers=headers) as session:
        while True:

            if len(SEEN) > 500:
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

                SEEN.add(tid)

                info = await _get_tournament_info(session, tid)
                if not info:
                    continue

                starts_at = info.get("startsAt")
                finishes_at = info.get("finishesAt")

                now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)

                if starts_at and finishes_at:
                    if int(starts_at) < now_ms < int(finishes_at):
                        _log(f"ONGOING — joining {tid}")
                        add_tournament(tid, TEAM)
                        continue

                if starts_at:
                    delta_sec = (int(starts_at) - now_ms) / 1000
                    if delta_sec <= 300:
                        _log(f"JOIN NOW {tid}, starts in {int(delta_sec)}s")
                        add_tournament(tid, TEAM)
                        continue

                    if delta_sec < 7200:
                        _log(f"Detected {tid}, starts in {int(delta_sec)}s")

            await asyncio.sleep(interval)


team_tournament_loop = realtime_team_scanner

if __name__ == "__main__":
    asyncio.run(realtime_team_scanner())
