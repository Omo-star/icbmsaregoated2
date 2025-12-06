import asyncio
import aiohttp
import datetime
from tournament_queue import get_pending, mark_processed

CHECK_INTERVAL = 30
PRE_STAGE_MINUTES = 10


def _alog(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[AutoTournament {ts}] {msg}")


async def get_tournament_start_time(tid: str) -> datetime.datetime | None:
    url = f"https://lichess.org/api/tournament/{tid}"
    _alog(f"Fetching start time for {tid} from {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _alog(f"HTTP {resp.status} from Lichess for {tid}")
                    return None

                data = await resp.json()

                if "startsAt" not in data:
                    _alog(f"startsAt missing in API response for {tid}")
                    return None

                starts_at = datetime.datetime.fromtimestamp(
                    data["startsAt"] / 1000,
                    tz=datetime.timezone.utc,
                )
                _alog(f"Tournament {tid} starts at {starts_at}")
                return starts_at

    except Exception as e:
        _alog(f"Exception while fetching tournament {tid}: {e}")
        return None


async def run_tournament(ui, tid: str, team: str | None):
    if team:
        _alog(f"Running tournament command: tournament {tid} {team}")
        await ui._handle_command(["tournament", tid, team])
    else:
        _alog(f"Running tournament command: tournament {tid}")
        await ui._handle_command(["tournament", tid])


async def auto_tournament_loop(ui):
    _alog("Auto-tournament loop started.")

    while True:
        pending = get_pending()
        _alog(f"Current pending queue: {pending}")

        if pending:
            _alog("Pending tournaments found -> stopping matchmaking.")
            ui.game_manager.stop_matchmaking()
        else:
            _alog("No pending tournaments -> ensuring matchmaking is running.")
            ui.game_manager.start_matchmaking()
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        entry = pending[0]
        tid = entry["id"]
        team = entry.get("team")

        _alog(f"Processing tournament: id={tid}, team={team}")

        start_time = await get_tournament_start_time(tid)
        if not start_time:
            _alog(f"Could not fetch valid start time for {tid}, marking processed and skipping.")
            # IMPORTANT: pass the ID string, NOT the dict
            mark_processed(tid)
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        now = datetime.datetime.now(datetime.timezone.utc)
        _alog(f"Now: {now}, start_time: {start_time}")

        if now >= start_time:
            _alog(f"Tournament {tid} already started — joining now!")
            ui.game_manager.stop_matchmaking()
            await run_tournament(ui, tid, team)

        else:
            pre_stage_time = start_time - datetime.timedelta(minutes=PRE_STAGE_MINUTES)
            _alog(f"Pre-stage time for {tid}: {pre_stage_time}")

            while datetime.datetime.now(datetime.timezone.utc) < pre_stage_time:
                _alog(f"Waiting for pre-stage for {tid} ...")
                ui.game_manager.start_matchmaking()
                await asyncio.sleep(CHECK_INTERVAL)

            _alog(f"Reached pre-stage for {tid}, stopping matchmaking.")
            ui.game_manager.stop_matchmaking()

            while datetime.datetime.now(datetime.timezone.utc) < start_time:
                _alog(f"Waiting for tournament {tid} to start ...")
                await asyncio.sleep(5)

            _alog(f"Start time reached for {tid}, joining now (team={team})")
            await run_tournament(ui, tid, team)

        _alog(f"Monitoring tournament {tid} until it finishes.")
        while True:
            await asyncio.sleep(20)
            if not ui.game_manager.tournament_id:
                break

        _alog(f"Tournament {tid} finished. Resuming matchmaking.")
        ui.game_manager.start_matchmaking()

        mark_processed(tid)
        _alog(f"Tournament {tid} removed from queue.")
