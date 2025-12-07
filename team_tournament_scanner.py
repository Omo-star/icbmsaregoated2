import asyncio
import aiohttp
import datetime
import re
from tournament_queue import add_tournament

TEAM = "darkonbot"
URL = f"https://lichess.org/team/{TEAM}"
REGEX = r"tournament/([A-Za-z0-9]{8})"
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

async def _get_info(session, tid):
    try:
        async with session.get(f"https://lichess.org/api/tournament/{tid}") as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

def _team_in_tournament(info):
    teams = []
    if "teamBattle" in info and "teams" in info["teamBattle"]:
        teams = [t.get("id") for t in info["teamBattle"]["teams"]]
    elif "teams" in info:
        teams = [t.get("id") for t in info["teams"]]
    return TEAM in teams

async def realtime_team_scanner(interval=30):
    headers = {"User-Agent": "BotLi-RealTimeScanner"}
    async with aiohttp.ClientSession(headers=headers) as session:
        _log("Started real-time team scanner")
        while True:
            if len(SEEN) > 200:
                SEEN.clear()

            html = await _fetch_html(session)
            ids = re.findall(REGEX, html)
            _log(f"Found {len(ids)} tournaments on page")

            for tid in ids:
                if tid in SEEN:
                    continue

                info = await _get_info(session, tid)
                if not info:
                    SEEN.add(tid)
                    continue

                status = info.get("status")
                start = info.get("startsAt")
                now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)

                if status == "started" and _team_in_tournament(info):
                    add_tournament(tid, TEAM)
                    _log(f"JOIN ONGOING {tid}")
                    SEEN.add(tid)
                    continue

                if start:
                    delta = (int(start) - now_ms) / 1000
                    if 0 < delta <= 300:
                        add_tournament(tid, TEAM)
                        _log(f"JOIN NOW {tid}, starts in {int(delta)}s")
                    elif delta < 7200:
                        _log(f"Detected {tid}, starts in {int(delta)}s")

                SEEN.add(tid)

            await asyncio.sleep(interval)

team_tournament_loop = realtime_team_scanner

if __name__ == "__main__":
    asyncio.run(realtime_team_scanner())
