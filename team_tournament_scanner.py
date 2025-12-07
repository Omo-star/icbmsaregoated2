import asyncio
import aiohttp
import datetime
import json
from tournament_queue import add_tournament

TEAM = "darkonbot"
SEEN = set()

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RTTeamScanner {ts}] {msg}")

async def fetch_team_tournaments(api, token):
    url = f"https://lichess.org/api/team/{TEAM}/tournaments?nb=200"

    headers = {
        "Accept": "application/x-ndjson",
        "Authorization": f"Bearer {token}",
        "User-Agent": "BotLi-RealTimeScanner"
    }

    try:
        r = await api.request("GET", url, headers=headers)

        if r.status != 200:
            _log(f"HTTP {r.status} fetching team tournaments")
            return []

        raw = await r.text()
        lines = raw.strip().split("\n")
        tournaments = []

        for line in lines:
            try:
                tournaments.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return tournaments

    except Exception as e:
        _log(f"Error fetching team tournaments: {e}")
        return []



async def realtime_team_scanner(api=None, interval=30):
    if api is None:
        _log("ERROR: realtime_team_scanner called without API reference!")
        return

    token = api.config.token 

    _log("Started real-time team scanner")

    while True:
        if len(SEEN) > 500:
            SEEN.clear()

        tournaments = await fetch_team_tournaments(api, token)


        if not tournaments:
            _log("No tournaments returned from API")
            await asyncio.sleep(interval)
            continue

        _log(f"Fetched {len(tournaments)} tournaments")

        now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)

        for t in tournaments:
            tid = t.get("id")
            if not tid or tid in SEEN:
                continue

            starts_at = t.get("startsAt")

            if not starts_at:
                SEEN.add(tid)
                continue

            delta = (int(starts_at) - now_ms) / 1000

            if delta <= 0:
                add_tournament(tid, TEAM)
                _log(f"JOIN NOW {tid}, tournament already started")
            elif delta <= 300:
                add_tournament(tid, TEAM)
                _log(f"JOIN NOW {tid}, starts in {int(delta)}s")
            else:
                _log(f"Detected {tid}, starts in {int(delta)}s")

            SEEN.add(tid)

        await asyncio.sleep(interval)


async def team_tournament_loop(api):
    return await realtime_team_scanner(api, interval=30)

