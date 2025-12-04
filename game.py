import asyncio
import chess
from typing import Any
from datetime import datetime
from api import API
from botli_dataclasses import GameInformation
from chatter import Chatter
from config import Config
from lichess_game import LichessGame
import json, os
from status_writer import write_status
import subprocess

def push_status():
    subprocess.run(["git", "add", "lichess_status.json"], check=True)
    subprocess.run(["git", "commit", "-m", "update status", "--allow-empty"], check=False)
    subprocess.run(["git", "push"], check=True)

streak_file = "streak.json"


class Game:
    def __init__(self, api: API, config: Config, username: str, game_id: str) -> None:
        self.api = api
        self.config = config
        self.username = username
        self.game_id = game_id

        self.takeback_count = 0
        self.was_aborted = False
        self.ejected_tournament: str | None = None

        self.move_task: asyncio.Task[None] | None = None
        self.abortion_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        game_stream_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task = asyncio.create_task(self.api.get_game_stream(self.game_id, game_stream_queue))
        info = GameInformation.from_game_full_event(await game_stream_queue.get())
        lichess_game = await LichessGame.acreate(self.api, self.config, self.username, info)
        chatter = Chatter(self.api, self.config, self.username, info, lichess_game)

        self._print_game_information(info)
        account = await self.api.get_account()
        ratings = {
            "blitz": account["perfs"]["blitz"]["rating"],
            "rapid": account["perfs"]["rapid"]["rating"],
            "bullet": account["perfs"]["bullet"]["rating"],
        }
        self.ratings = ratings


        if info.state["status"] != "started":
            self._print_result_message(info.state, lichess_game, info)
            await chatter.send_goodbyes()
            await lichess_game.close()
            return

        await chatter.send_greetings()

        if lichess_game.is_our_turn:
            await self._make_move(lichess_game, chatter)
        else:
            await lichess_game.start_pondering()

        max_takebacks = 0 if info.opponent_is_bot else self.config.challenge.max_takebacks
        if info.tournament_id is None:
            abortion_seconds = 30 if info.opponent_is_bot else 60
            self.abortion_task = asyncio.create_task(self._abortion_task(lichess_game, chatter, abortion_seconds))

        while event := await game_stream_queue.get():
            match event["type"]:
                case "chatLine":
                    await chatter.handle_chat_message(event, self.takeback_count, max_takebacks)
                    continue
                case "opponentGone":
                    if not self.move_task and event.get("claimWinInSeconds") == 0:
                        if lichess_game.has_insufficient_material:
                            await self.api.claim_draw(self.game_id)
                        else:
                            await self.api.claim_victory(self.game_id)
                    continue
                case "gameFull":
                    event = event["state"]

            if event.get("wtakeback") or event.get("btakeback"):
                if self.takeback_count >= max_takebacks:
                    await self.api.handle_takeback(self.game_id, False)
                    continue

                if await self.api.handle_takeback(self.game_id, True):
                    if self.move_task:
                        self.move_task.cancel()
                        self.move_task = None
                    await lichess_game.takeback()
                    self.takeback_count += 1
                continue

            has_updated = lichess_game.update(event)
            status = {
                "online": True,
                "playing": True,
                "rating": self.ratings.get(info.speed, self.ratings["blitz"]),
                "opponent": info.black_name if lichess_game.is_white else info.white_name,
                "variant": info.variant_str,
                "time_control": info.tc_format,
                "time_left": int(lichess_game.white_time if lichess_game.is_white else lichess_game.black_time),
                "timestamp": datetime.utcnow().isoformat()
            }
            write_status(status)

            if event["status"] != "started":
                if self.move_task:
                    self.move_task.cancel()

                self._print_result_message(event, lichess_game, info)
                await chatter.send_goodbyes()
                break

            if has_updated:
                self.move_task = asyncio.create_task(self._make_move(lichess_game, chatter))

        if self.abortion_task:
            self.abortion_task.cancel()
        await lichess_game.close()

    async def _make_move(self, lichess_game: LichessGame, chatter: Chatter) -> None:
        lichess_move = await lichess_game.make_move()
        if lichess_move.resign:
            await self.api.resign_game(self.game_id)
        else:
            await self.api.send_move(self.game_id, lichess_move.uci_move, lichess_move.offer_draw)
            await chatter.print_eval()
        self.move_task = None

    async def _abortion_task(self, lichess_game: LichessGame, chatter: Chatter, abortion_seconds: int) -> None:
        await asyncio.sleep(abortion_seconds)

        if not lichess_game.is_our_turn and lichess_game.is_abortable:
            print("Aborting game ...")
            await self.api.abort_game(self.game_id)
            await chatter.send_abortion_message()

        self.abortion_task = None

    @staticmethod
    def _print_game_information(info: GameInformation) -> None:
        opponents_str = f"{info.white_str}   -   {info.black_str}"
        message = " • ".join([info.id_str, opponents_str, info.tc_format, info.rated_str, info.variant_str])

        print(f"\n{message}\n{128 * '‾'}")

    def _print_result_message(
        self, game_state: dict[str, Any], lichess_game: LichessGame, info: GameInformation
    ) -> None:

        if os.path.exists(streak_file):
            streak = json.load(open(streak_file))
        else:
            streak = {"current": 0}

        if winner := game_state.get("winner"):
            if winner == "white":
                message = f"{info.white_name} won"
                loser = info.black_name
                white_result = "1"
                black_result = "0"
                winner_name = info.white_name
            else:
                message = f"{info.black_name} won"
                loser = info.white_name
                white_result = "0"
                black_result = "1"
                winner_name = info.black_name

            if winner_name == self.username:
                streak["current"] += 1
            else:
                streak["current"] = 0

            match game_state["status"]:
                case "mate":
                    message += " by checkmate!"
                case "outoftime":
                    message += f"! {loser} ran out of time."
                case "resign":
                    message += f"! {loser} resigned."
                case "variantEnd":
                    message += " by variant rules!"
                case "timeout":
                    message += f"! {loser} timed out."
                case "noStart":
                    if loser == self.username:
                        self.ejected_tournament = info.tournament_id
                    message += f"! {loser} has not started the game."

        else:
            white_result = "½"
            black_result = "½"
            winner = None

            match game_state["status"]:
                case "draw":
                    if lichess_game.board.is_fifty_moves():
                        message = "Game drawn by 50-move rule."
                    elif lichess_game.board.is_repetition():
                        message = "Game drawn by threefold repetition."
                    elif lichess_game.board.is_insufficient_material():
                        message = "Game drawn due to insufficient material."
                    elif lichess_game.board.is_variant_draw():
                        message = "Game drawn by variant rules."
                    else:
                        message = "Game drawn by agreement."
                case "stalemate":
                    message = "Game drawn by stalemate."
                case "outoftime":
                    out_of_time_player = info.black_name if game_state["wtime"] else info.white_name
                    message = f"Game drawn. {out_of_time_player} ran out of time."
                case "insufficientMaterialClaim":
                    message = "Game drawn due to insufficient material claim."
                case "timeout":
                    message = "Game drawn. One player left the game."
                case _:
                    self.was_aborted = True
                    message = "Game aborted."
                    white_result = "X"
                    black_result = "X"

            streak["current"] = 0

        json.dump(streak, open(streak_file, "w"), indent=2)

        opponents_str = f"{info.white_str} {white_result} - {black_result} {info.black_str}"
        message = " • ".join([info.id_str, opponents_str, message])
        print(f"{message}\n{128 * '‾'}")

        temp_board = chess.Board(info.initial_fen, chess960=(info.variant == Variant.CHESS960))
        moves_san = []
        for uci in info.state["moves"].split():
            m = chess.Move.from_uci(uci)
            moves_san.append(temp_board.san(m))
            temp_board.push(m)
        moves_str = " ".join(moves_san)

        if winner_name == self.username:
            result_text = "win"
        elif winner_name is None:
            result_text = "draw"
        else:
            result_text = "loss"

        last_game = {
            "result": result_text,
            "opponent": info.black_name if lichess_game.is_white else info.white_name,
            "rating_before": self.ratings[info.speed],
            "rating_after": self.ratings[info.speed],
            "rating_delta": 0,
            "moves": moves_str,
            "duration": int(info.state["wtime"] + info.state["btime"]),
            "bot_color": "white" if lichess_game.is_white else "black",
            "termination": game_state["status"]
        }

        write_status({
            "online": True,
            "playing": False,
            "last_game": last_game,
            "timestamp": datetime.utcnow().isoformat()
        })

        push_status()


