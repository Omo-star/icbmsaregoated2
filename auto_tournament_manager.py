import asyncio
import aiohttp
import datetime
from tournament_queue import get_pending, mark_processed

CHECK_INTERVAL = 30
PRE_STAGE_MINUTES = 10


async def get_tournament_start_time(tid: str) -> datetime.datetime | None:
    url = f"https://lichess.org/api/tournament/{tid}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None

            data = await resp.json()

            if "startsAt" not in data:
                return None

            return datetime.datetime.fromtimestamp(data["startsAt"] / 1000, tz=datetime.timezone.utc)


async def run_tournament(ui, tid: str, team: str | None):
    if team:
        await ui._handle_command(["tournament", tid, team])
    else:
        await ui._handle_command(["tournament", tid])


async def auto_tournament_loop(ui):
    while True:
        pending = get_pending()

        if pending:
            ui.game_manager.stop_matchmaking()
        else:
            ui.game_manager.start_matchmaking()
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        entry = pending[0]
        tid = entry["id"]
        team = entry.get("team")

        start_time = await get_tournament_start_time(tid)
        if not start_time:
            print(f"[AutoTournament] Could not fetch info for {tid}, skipping.")
            mark_processed(entry)
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        now = datetime.datetime.now(datetime.timezone.utc)

        if now > start_time:
            print(f"[AutoTournament] Tournament {tid} already started — joining now!")
            ui.game_manager.stop_matchmaking()
            await run_tournament(ui, tid, team)

        else:
            pre_stage_time = start_time - datetime.timedelta(minutes=PRE_STAGE_MINUTES)

            while datetime.datetime.now(datetime.timezone.utc) < pre_stage_time:
                ui.game_manager.start_matchmaking()
                await asyncio.sleep(CHECK_INTERVAL)

            ui.game_manager.stop_matchmaking()

            while datetime.datetime.utcnow() < start_time:
                await asyncio.sleep(5)

            print(f"[AutoTournament] Joining tournament {tid} (team={team})...")
            await run_tournament(ui, tid, team)

        while True:
            await asyncio.sleep(20)
            if not ui.game_manager.tournament_id:
                break

        print(f"[AutoTournament] Tournament {tid} finished. Resuming matchmaking.")
        ui.game_manager.start_matchmaking()

        mark_processed(tid)
