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
            return datetime.datetime.fromtimestamp(data["startsAt"] / 1000)


async def run_tournament(ui, tid: str):
    await ui._handle_command(["tournament", tid])


async def auto_tournament_loop(ui):
    while True:
        pending = get_pending()
        if not pending:
            ui.game_manager.start_matchmaking()
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        tid = pending[0]

        start_time = await get_tournament_start_time(tid)
        if not start_time:
            mark_processed(tid)
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        now = datetime.datetime.utcnow()
        pre_stage_time = start_time - datetime.timedelta(minutes=PRE_STAGE_MINUTES)

        while datetime.datetime.utcnow() < pre_stage_time:
            ui.game_manager.start_matchmaking()
            await asyncio.sleep(CHECK_INTERVAL)

        ui.game_manager.stop_matchmaking()

        while datetime.datetime.utcnow() < start_time:
            await asyncio.sleep(5)

        await run_tournament(ui, tid)

        while True:
            await asyncio.sleep(20)
            if not ui.game_manager.tournament_id:
                break

        ui.game_manager.start_matchmaking()
        mark_processed(tid)
