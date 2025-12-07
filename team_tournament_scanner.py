import asyncio
import aiohttp
import datetime
import re
from tournament_queue import add_tournament

TEAMS = [
    "darkonbot"
]

TOURNAMENT_REGEX = r"lichess\.org/tournament/([A-Za-z0-9]{8})(?:\?team=([\w-]+))?"

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[TeamScanner {ts}] {msg}")

async def _fetch_team_page(session, team_id):
    url = f"https://lichess.org/team/{team_id}"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                _log(f"HTTP {resp.status} for team {team_id}")
                return ""
            return await resp.text()
    except Exception as e:
        _log(f"Error fetching team {team_id}: {e}")
        return ""

def _extract_tournaments_html(html):
    matches = re.findall(TOURNAMENT_REGEX, html)
    out = []
    for tid, team in matches:
        out.append((tid, team or None))
    return out

async def scan_teams_once(team_ids=None):
    ids = team_ids or TEAMS
    if not ids:
        _log("No teams configured")
        return

    headers = {
        "User-Agent": "BotLi-TeamScanner",
        "Accept": "text/html"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        for team_id in ids:
            html = await _fetch_team_page(session, team_id)
            if not html:
                continue
            for tid, team in _extract_tournaments_html(html):
                add_tournament(tid, team)
                _log(f"Discovered tournament {tid} from team {team_id} team_param={team}")

async def team_tournament_loop(interval_seconds=3600, team_ids=None):
    while True:
        await scan_teams_once(team_ids)
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    asyncio.run(team_tournament_loop())
