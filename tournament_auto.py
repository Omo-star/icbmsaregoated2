import asyncio
from tournament_queue import get_pending, mark_processed

CHECK_INTERVAL_SECONDS = 30


async def process_tournament_command(ui, tid: str):
    print(f"[TournamentAuto] Auto-joining tournament {tid}...")
    await ui._handle_command(["tournament", tid])
    print(f"[TournamentAuto] Submitted join request for {tid}")


async def tournament_auto_loop(ui):
    print("[TournamentAuto] Tournament auto-join loop started")
    while True:
        pending = get_pending()
        for tid in pending:
            try:
                await process_tournament_command(ui, tid)
            except Exception as e:
                print(f"[TournamentAuto] Error processing {tid}: {e}")
            finally:
                mark_processed(tid)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
