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

async def fetch_team_tournaments(session, token):
    url = f"https://lichess.org/api/team/{TEAM}/tournaments?nb=200"
    headers = {
        "Accept": "application/x-ndjson",
        "Authorization": f"Bearer {token}",
        "User-Agent": "BotLi-RealTimeScanner"
    }

    try:
        async with session.get(url, headers=headers) as r:
            if r.status != 200:
                _log(f"HTTP {r.status} fetching tournaments")
                text = await r.text()
                if text:
                    _log(f"Body preview: {text[:200].replace(chr(10), ' ')}")
                return []

            raw = await r.text()
            if not raw.strip():
                _log("Empty NDJSON response")
                return []

            tournaments = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except:
                    continue
                tournaments.append(obj)

            return tournaments

    except Exception as e:
        _log(f"Error fetching tournaments: {e}")
        return []

async def realtime_team_scanner(token, interval=30):
    if not token:
        _log("ERROR: realtime_team_scanner called without token")
        return

    _log("Started real-time team scanner")

    async with aiohttp.ClientSession() as session:
        while True:
            if len(SEEN) > 500:
                SEEN.clear()

            tournaments = await fetch_team_tournaments(session, token)

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

                try:
                    delta = (int(starts_at) - now_ms) / 1000
                except:
                    SEEN.add(tid)
                    continue

                if delta <= 0:
                    add_tournament(tid, TEAM)
                    _log(f"JOIN NOW {tid}, already started")
                elif delta <= 300:
                    add_tournament(tid, TEAM)
                    _log(f"JOIN NOW {tid}, starts in {int(delta)}s")
                else:
                    _log(f"Detected {tid}, starts in {int(delta)}s")

                SEEN.add(tid)

            await asyncio.sleep(interval)

async def team_tournament_loop(token):
    await realtime_team_scanner(token, interval=30)
