import asyncio
import aiohttp
import datetime
from tournament_queue import get_pending, mark_processed

CHECK_INTERVAL = 30
PRE_STAGE_MINUTES = 10


def _alog(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[AutoTournament {ts}] {msg}")


async def fetch_tournament_info(tid: str):
    url = f"https://lichess.org/api/tournament/{tid}"
    _alog(f"Fetching tournament info for {tid} ...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _alog(f"HTTP {resp.status} from Lichess for {tid}")
                    return None
                return await resp.json()

    except Exception as e:
        _alog(f"Exception while fetching tournament {tid}: {e}")
        return None


def parse_lichess_time(raw):
    if isinstance(raw, str):
        raw = raw.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(raw)
    else:
        return datetime.datetime.fromtimestamp(raw / 1000, tz=datetime.timezone.utc)


async def run_tournament(ui, tid: str, team: str | None):
    try:
        if team:
            ok = await ui.api.join_tournament(tid, team, None)
            if not ok:
                _alog(f"Team join failed for {tid}")
                return False
        else:
            _alog(f"Joining tournament: tournament {tid}")
            await ui._handle_command(["tournament", tid])
        return True   

    except Exception as e:
        _alog(f"Join command failed for {tid}: {e}")
        return False


async def auto_tournament_loop(ui):
    _alog("Auto-tournament loop started.")
    await asyncio.sleep(1.0)
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

        data = await fetch_tournament_info(tid)
        if not data:
            _alog(f"Failed to load tournament {tid}, skipping.")
            mark_processed(tid)
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        system = data.get("system", "arena")
        is_finished = data.get("isFinished", False)
        starts_at = parse_lichess_time(data["startsAt"])
        now = datetime.datetime.now(datetime.timezone.utc)

        _alog(f"System={system}, isFinished={is_finished}, startsAt={starts_at}, now={now}")

        if system == "arena":
            if is_finished:
                _alog(f"Arena {tid} already finished — removing.")
                mark_processed(tid)
                continue

            _alog(f"Arena {tid} is joinable now — joining!")
            ui.game_manager.stop_matchmaking()
            await asyncio.sleep(0.5)
            success = await run_tournament(ui, tid, team)

            if not success:
                _alog(f"Join reported failure, but bot may have already joined. Removing.")
                mark_processed(tid)
                continue

        else:
            if now >= starts_at:
                _alog(f"Swiss/team battle {tid} already started — cannot join.")
                mark_processed(tid)
                continue

            pre_stage = starts_at - datetime.timedelta(minutes=PRE_STAGE_MINUTES)
            _alog(f"Pre-stage window begins at {pre_stage}")

            while datetime.datetime.now(datetime.timezone.utc) < pre_stage:
                _alog(f"Waiting for pre-stage for {tid} ...")
                ui.game_manager.start_matchmaking()
                await asyncio.sleep(CHECK_INTERVAL)

            _alog(f"Reached pre-stage for {tid}, stopping matchmaking.")
            ui.game_manager.stop_matchmaking()

            while datetime.datetime.now(datetime.timezone.utc) < starts_at:
                _alog(f"Waiting for Swiss {tid} to start...")
                await asyncio.sleep(5)

            _alog(f"Swiss {tid} starting — joining now!")
            await run_tournament(ui, tid, team)

        _alog(f"Monitoring tournament {tid} until it finishes...")

        while True:
            await asyncio.sleep(20)
            if not ui.game_manager.tournament_id:
                break   

        _alog(f"Tournament {tid} finished. Resuming matchmaking.")
        ui.game_manager.start_matchmaking()

        mark_processed(tid)
        _alog(f"Tournament {tid} removed from queue.")
