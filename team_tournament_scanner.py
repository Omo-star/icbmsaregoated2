import asyncio
import aiohttp
import datetime
from tournament_queue import add_tournament

TEAM = "darkonbot"
API_URL = f"https://lichess.org/api/team/{TEAM}/arena"
SEEN = set()

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RTTeamScanner {ts}] {msg}")

async def _fetch_team_tournaments(session):
    try:
        async with session.get(API_URL) as r:
            if r.status != 200:
                return []
            return await r.json()
    except:
        return []

async def realtime_team_scanner(interval=30):
    headers = {"User-Agent": "BotLi-RealTimeScanner"}
    async with aiohttp.ClientSession(headers=headers) as session:
        _log("Started real-time team scanner")

        while True:
            if len(SEEN) > 200:
                SEEN.clear()

            tournaments = await _fetch_team_tournaments(session)
            _log(f"Fetched {len(tournaments)} tournaments from API")

            now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)

            for t in tournaments:
                tid = t.get("id")
                if not tid or tid in SEEN:
                    continue

                status = t.get("status")
                starts_at = t.get("startsAt")

                if status == "started":
                    add_tournament(tid, TEAM)
                    _log(f"JOIN NOW {tid} (ongoing)")
                elif starts_at:
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
