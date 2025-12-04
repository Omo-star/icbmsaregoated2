import argparse
import asyncio
import logging
import os
import signal
import sys
from enum import StrEnum
from typing import TypeVar

from api import API
from botli_dataclasses import ChallengeRequest
from config import Config
from engine import Engine
from enums import ChallengeColor, PerfType, Variant
from event_handler import EventHandler
from game_manager import GameManager
from logo import LOGO

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

console = Console()

COMMANDS = {
    "blacklist": "Temporarily blacklists a user. Use config for permanent blacklisting. Usage: blacklist USERNAME",
    "challenge": "Challenges a player. Usage: challenge USERNAME [TIMECONTROL] [COLOR] [RATED] [VARIANT]",
    "clear": "Clears the challenge queue.",
    "create": "Challenges a player to COUNT game pairs. Usage: create COUNT USERNAME [TIMECONTROL] [RATED] [VARIANT]",
    "help": "Prints this message.",
    "join": "Joins a team. Usage: join TEAM_ID [PASSWORD]",
    "leave": "Leaves tournament. Usage: leave ID",
    "matchmaking": "Starts matchmaking mode.",
    "quit": "Exits the bot.",
    "rechallenge": "Challenges the opponent to the last received challenge.",
    "reset": "Resets matchmaking. Usage: reset PERF_TYPE",
    "stop": "Stops matchmaking mode.",
    "tournament": "Joins tournament. Usage: tournament ID [TEAM_ID] [PASSWORD]",
    "whitelist": "Temporarily whitelists a user. Use config for permanent whitelisting. Usage: whitelist USERNAME",
}

EnumT = TypeVar("EnumT", bound=StrEnum)


class UserInterface:
    async def main(self, commands: list[str], config_path: str, allow_upgrade: bool) -> None:
        self.config = Config.from_yaml(config_path)

        async with API(self.config) as self.api:
            account = await self.api.get_account()
            username: str = account["username"]

            console.print(Panel.fit(LOGO, style="cyan"))
            console.print(Rule(f"[magenta]BotLi {self.config.version}[/magenta]"))
            console.print(f"Logged in as [bold green]{username}[/bold green]\n")

            self.api.append_user_agent(username)
            await self._handle_bot_status(account.get("title"), allow_upgrade)
            await self._test_engines()
            await self._download_online_blacklists()

            self.game_manager = GameManager(self.api, self.config, username)
            self.game_manager_task = asyncio.create_task(self.game_manager.run())

            self.event_handler = EventHandler(self.api, self.config, username, self.game_manager)
            self.event_handler_task = asyncio.create_task(self.event_handler.run())

            signal.signal(signal.SIGTERM, self.signal_handler)

            if commands:
                await asyncio.sleep(0.5)
                for command in commands:
                    parts = command.split()
                    if parts:
                        await self._handle_command(parts)

            if not sys.stdin.isatty():
                await self.game_manager_task
                return

            history_path = os.path.expanduser("~/.botli_history")
            completer = WordCompleter(list(COMMANDS.keys()), ignore_case=True, sentence=True)
            history = FileHistory(history_path)
            self.session = PromptSession(completer=completer, history=history)

            with patch_stdout():
                while True:
                    try:
                        line = await self.session.prompt_async("[bold magenta]botli> [/bold magenta]")
                    except (EOFError, KeyboardInterrupt):
                        await self._quit()
                        break
                    command = line.split()
                    if command:
                        await self._handle_command(command)

    async def _handle_bot_status(self, title: str | None, allow_upgrade: bool) -> None:
        scopes = await self.api.get_token_scopes(self.config.token)
        if "bot:play" not in scopes:
            console.print(
                "\n[red]Your token is missing the bot:play scope. This is mandatory to use BotLi.[/red]\n"
                "You can create such a token by following this link:\n"
                "https://lichess.org/account/oauth/token/create?scopes[]=bot:play&description=BotLi"
            )
            sys.exit(1)

        if title == "BOT":
            return

        console.print("\n[red]BotLi can only be used by BOT accounts![/red]\n")

        if not sys.stdin.isatty() and not allow_upgrade:
            console.print(
                'Start BotLi with the "[bold]--upgrade[/bold]" flag if you are sure you want to upgrade this account.\n'
                "[yellow]WARNING: This is irreversible. The account will only be able to play as a BOT.[/yellow]"
            )
            sys.exit(1)
        elif sys.stdin.isatty():
            console.print(
                "This will upgrade your account to a BOT account.\n"
                "[yellow]WARNING: This is irreversible. The account will only be able to play as a BOT.[/yellow]"
            )
            approval = await asyncio.to_thread(input, "Do you want to continue? [y/N]: ")

            if approval.lower() not in {"y", "yes"}:
                console.print("[yellow]Upgrade aborted.[/yellow]")
                sys.exit()

        if await self.api.upgrade_account():
            console.print("[bold green]Upgrade successful.[/bold green]")
        else:
            console.print("[red]Upgrade failed.[/red]")
            sys.exit(1)

    async def _test_engines(self) -> None:
        if not self.config.engines:
            console.print("[yellow]No engines configured.[/yellow]")
            return

        console.print("[bold cyan]Testing engines...[/bold cyan]")
        for engine_name, engine_config in self.config.engines.items():
            console.print(f"  [white]- {engine_name}[/white] ", end="")
            await Engine.test(engine_config)
            console.print("[bold green]OK[/bold green]")

        console.print()

    async def _download_online_blacklists(self) -> None:
        for url in self.config.online_blacklists:
            online_blacklist = await self.api.download_blacklist(url) or []
            online_blacklist = [
                username for username in map(str.lower, online_blacklist) if username not in self.config.whitelist
            ]
            self.config.blacklist.extend(online_blacklist)
            console.print(f'Blacklisted [bold]{len(online_blacklist)}[/bold] users from "[magenta]{url}[/magenta]".')

    async def _handle_command(self, command: list[str]) -> None:
        match command[0]:
            case "blacklist":
                self._blacklist(command)
            case "challenge":
                self._challenge(command)
            case "clear":
                self._clear()
            case "create":
                self._create(command)
            case "join":
                await self._join(command)
            case "leave":
                self._leave(command)
            case "matchmaking" | "m":
                self._matchmaking()
            case "quit" | "exit" | "q":
                await self._quit()
                sys.exit()
            case "rechallenge":
                self._rechallenge()
            case "reset":
                self._reset(command)
            case "stop" | "s":
                self._stop()
            case "tournament" | "t":
                self._tournament(command)
            case "whitelist":
                self._whitelist(command)
            case "help":
                self._help()
            case _:
                console.print(f"[red]Unknown command:[/red] '{command[0]}'")
                suggestions = [c for c in COMMANDS if c.startswith(command[0][0])]
                if suggestions:
                    console.print("Did you mean:")
                    for s in suggestions:
                        console.print(f"  • [green]{s}[/green]")
                    console.print()
                self._help()

    def _blacklist(self, command: list[str]) -> None:
        if len(command) != 2:
            console.print(COMMANDS["blacklist"])
            return

        self.config.blacklist.append(command[1].lower())
        console.print(f"Added [bold]{command[1]}[/bold] to the blacklist.")

    def _challenge(self, command: list[str]) -> None:
        if len(command) < 2:
            console.print(COMMANDS["challenge"])
            return

        try:
            challenge_request = ChallengeRequest.parse_from_command(command[1:], 60)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return

        self.game_manager.request_challenge(challenge_request)
        console.print(
            f"Challenge against [bold]{challenge_request.opponent_username}[/bold] added to the queue."
        )

    def _clear(self) -> None:
        self.game_manager.challenge_requests.clear()
        console.print("[yellow]Challenge queue cleared.[/yellow]")

    def _create(self, command: list[str]) -> None:
        if len(command) < 3:
            console.print(COMMANDS["create"])
            return

        try:
            count = int(command[1])
        except ValueError:
            console.print("[red]First argument must be the number of game pairs to create.[/red]")
            return

        try:
            challenge_request = ChallengeRequest.parse_from_command(command[2:], 60)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return

        challenges: list[ChallengeRequest] = []
        for _ in range(count):
            challenges.extend(
                (
                    challenge_request.replaced(color=ChallengeColor.WHITE),
                    challenge_request.replaced(color=ChallengeColor.BLACK),
                )
            )

        self.game_manager.request_challenge(*challenges)
        console.print(
            f"Challenges for [bold]{count}[/bold] game pairs against "
            f"[bold]{challenge_request.opponent_username}[/bold] added to the queue."
        )

    async def _join(self, command: list[str]) -> None:
        if len(command) < 2 or len(command) > 3:
            console.print(COMMANDS["join"])
            return

        password = command[2] if len(command) > 2 else None
        if await self.api.join_team(command[1], password):
            console.print(f'Joined team "[bold]{command[1]}[/bold]" successfully.')

    def _leave(self, command: list[str]) -> None:
        if len(command) != 2:
            console.print(COMMANDS["leave"])
            return

        self.game_manager.request_tournament_leaving(command[1])
        console.print(f"Requested leaving tournament [bold]{command[1]}[/bold].")

    def _matchmaking(self) -> None:
        console.print("[bold cyan]Starting matchmaking...[/bold cyan]")
        self.game_manager.start_matchmaking()

    async def _quit(self) -> None:
        self.game_manager.stop()
        console.print("[yellow]Terminating program...[/yellow]")
        self.event_handler_task.cancel()
        await self.game_manager_task

    def _rechallenge(self) -> None:
        last_challenge_event = self.event_handler.last_challenge_event
        if last_challenge_event is None:
            console.print("[yellow]No last challenge available.[/yellow]")
            return

        if last_challenge_event["speed"] == "correspondence":
            console.print("[yellow]Correspondence is not supported by BotLi.[/yellow]")
            return

        opponent_username: str = last_challenge_event["challenger"]["name"]
        initial_time: int = last_challenge_event["timeControl"]["limit"]
        increment: int = last_challenge_event["timeControl"]["increment"]
        rated: bool = last_challenge_event["rated"]
        event_color: str = last_challenge_event["color"]
        variant = Variant(last_challenge_event["variant"]["key"])

        if event_color == "white":
            color = ChallengeColor.BLACK
        elif event_color == "black":
            color = ChallengeColor.WHITE
        else:
            color = ChallengeColor.RANDOM

        challenge_request = ChallengeRequest(opponent_username, initial_time, increment, rated, color, variant, 300)
        self.game_manager.request_challenge(challenge_request)
        console.print(
            f"Challenge against [bold]{challenge_request.opponent_username}[/bold] added to the queue."
        )

    def _reset(self, command: list[str]) -> None:
        if len(command) != 2:
            console.print(COMMANDS["reset"])
            return

        try:
            perf_type = self._find_enum(command[1], PerfType)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return

        self.game_manager.matchmaking.opponents.reset_release_time(perf_type)
        console.print("[yellow]Matchmaking has been reset.[/yellow]")

    def _stop(self) -> None:
        if self.game_manager.stop_matchmaking():
            console.print("[yellow]Stopping matchmaking...[/yellow]")
        else:
            console.print("[yellow]Matchmaking isn't currently running.[/yellow]")

    def _tournament(self, command: list[str]) -> None:
        if len(command) < 2 or len(command) > 4:
            console.print(COMMANDS["tournament"])
            return

        tournament_id = command[1]
        tournament_team = command[2] if len(command) > 2 else None
        tournament_password = command[3] if len(command) > 3 else None

        self.game_manager.request_tournament_joining(tournament_id, tournament_team, tournament_password)
        console.print(
            f"Requested joining tournament [bold]{tournament_id}[/bold]"
            + (f" with team [bold]{tournament_team}[/bold]" if tournament_team else "")
        )

    def _whitelist(self, command: list[str]) -> None:
        if len(command) != 2:
            console.print(COMMANDS["whitelist"])
            return

        self.config.whitelist.append(command[1].lower())
        console.print(f"Added [bold]{command[1]}[/bold] to the whitelist.")

    @staticmethod
    def _help() -> None:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Command", style="green", no_wrap=True)
        table.add_column("Description", style="white")
        for cmd, desc in COMMANDS.items():
            table.add_row(cmd, desc)
        console.print("\n[bold cyan]Available BotLi Commands:[/bold cyan]\n")
        console.print(table)
        console.print()

    @staticmethod
    def _find_enum(name: str, enum_type: type[EnumT]) -> EnumT:
        for enum in enum_type:
            if enum.lower() == name.lower():
                return enum
        raise ValueError(f"{name} is not a valid {enum_type}")

    def signal_handler(self, *_) -> None:
        self._quit_task = asyncio.create_task(self._quit())


class Autocompleter:
    def __init__(self, options: list[str]) -> None:
        self.options = options
        self.matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            if text:
                self.matches = [s for s in self.options if s and s.startswith(text)]
            else:
                self.matches = self.options[:]
        try:
            return self.matches[state]
        except IndexError:
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("commands", nargs="*", help="Commands that BotLi executes.")
    parser.add_argument("--config", "-c", default="config.yml", help="Path to config.yml.")
    parser.add_argument("--upgrade", "-u", action="store_true", help="Upgrade account to BOT account.")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    asyncio.run(UserInterface().main(args.commands, args.config, args.upgrade), debug=args.debug)
