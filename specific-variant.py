import requests
import io
import random
import chess
import chess.pgn
import chess.polyglot
import chess.variant

VARIANT = "chess960"
MAX_PLY = 50
MAX_BOOK_WEIGHT = 2520
MIN_RATING = 2400

BOOK_OUTPUT = "chess960.bin"
BOTS = {
    "LeelaMultiPoss","JAXMAN_N","PINEAPPLEMASK","Chrysogenum","Ghost_HunteR2998",
    "strain-on-veins","InvinxibleFlxsh","VEER-OMEGA-BOT","TestingBot1","RedHotBot",
    "ToromBot","Bharat_royals","pangubot","ElPeonElectrico","DarkOnBot","MaggiChess16",
    "YoBot_v2","TacticalBot","Bot1nokk","tbhOnBot","Speeedrunchessgames","NecroMindX",
    "Endogenetic-Bot","Exogenetic-Bot"
}


class BookMove:
    def __init__(self):
        self.weight = 0
        self.move: chess.Move | None = None


class BookPosition:
    def __init__(self):
        self.moves: dict[str, BookMove] = {}

    def get_move(self, uci: str) -> BookMove:
        return self.moves.setdefault(uci, BookMove())


class Book:
    def __init__(self):
        self.positions: dict[str, BookPosition] = {}

    def get_position(self, key_hex: str) -> BookPosition:
        return self.positions.setdefault(key_hex, BookPosition())

    def normalize(self):
        for pos in self.positions.values():
            s = sum(bm.weight for bm in pos.moves.values())
            if s <= 0:
                continue
            for bm in pos.moves.values():
                bm.weight = max(1, int(bm.weight / s * MAX_BOOK_WEIGHT))

    def save_polyglot(self, path: str):
        entries = []
        for key_hex, pos in self.positions.items():
            zbytes = bytes.fromhex(key_hex)
            for bm in pos.moves.values():
                if bm.weight <= 0 or bm.move is None:
                    continue
                m = bm.move
                if "@" in m.uci():
                    continue
                mi = m.to_square + (m.from_square << 6)
                if m.promotion:
                    mi += ((m.promotion - 1) << 12)
                mbytes = mi.to_bytes(2, "big")
                wbytes = min(MAX_BOOK_WEIGHT, bm.weight).to_bytes(2, "big")
                lbytes = (0).to_bytes(4, "big")
                entries.append(zbytes + mbytes + wbytes + lbytes)
        entries.sort(key=lambda e: (e[:8], e[10:12]))
        with open(path, "wb") as f:
            for e in entries:
                f.write(e)
        print(f"Saved {len(entries)} moves to book: {path}")


def key_hex(board: chess.Board) -> str:
    return f"{chess.polyglot.zobrist_hash(board):016x}"


def stream_user_games(username: str, variant: str = VARIANT, max_per_request: int = 300):
    url = f"https://lichess.org/api/games/user/{username}"
    headers = {"Accept": "application/x-chess-pgn"}
    session = requests.Session()
    until = None
    while True:
        params = {
            "moves": True,
            "analysed": False,
            "max": max_per_request,
            "variant": variant,
            "rated": "true",
        }
        if until is not None:
            params["until"] = int(until)
        resp = session.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        text = resp.text
        if not text.strip():
            break
        yield text
        tail = text[-2000:]
        import re
        m = re.search(r'\[EndTimeMillis\s+"?(\d{12,})"?\]', tail)
        if m:
            try:
                ts = int(m.group(1))
                until = ts - 1
                continue
            except Exception:
                pass
        m2 = re.search(r'\[UTCDate\s+"(\d{4}\.\d{2}\.\d{2})"\]\s*\[UTCTime\s+"(\d{2}:\d{2}:\d{2})"\]', tail)
        if m2:
            dt_str = m2.group(1).replace(".", "-") + " " + m2.group(2)
            try:
                import datetime
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                until = int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) - 1
                continue
            except Exception:
                pass
        break


def build_book(bin_path: str):
    book = Book()
    processed = kept = 0

    for bot in BOTS:
        try:
            for pgn_chunk in stream_user_games(bot):
                stream = io.StringIO(pgn_chunk)
                while True:
                    game = chess.pgn.read_game(stream)
                    if game is None:
                        break
                    processed += 1
                    variant_tag = (game.headers.get("Variant", "") or "").lower()
                    if VARIANT not in variant_tag and "chess960" not in variant_tag:
                        continue
                    white = game.headers.get("White", "")
                    black = game.headers.get("Black", "")
                    try:
                        white_elo = int(game.headers.get("WhiteElo", 0))
                        black_elo = int(game.headers.get("BlackElo", 0))
                    except ValueError:
                        continue
                    if white_elo < MIN_RATING or black_elo < MIN_RATING:
                        continue
                    mainline_moves = list(game.mainline_moves())
                    if not mainline_moves:
                        continue
                    kept += 1
                    starting_fen = None
                    if (game.headers.get("SetUp", "") or "") == "1" and game.headers.get("FEN"):
                        starting_fen = game.headers.get("FEN")
                    if starting_fen:
                        board = chess.Board(fen=starting_fen, chess960=True)
                    else:
                        try:
                            b = game.board()
                            board = chess.Board(b.fen(), chess960=True)
                        except Exception:
                            board = chess.Board(chess960=True)
                    result = game.headers.get("Result", "")
                    if result == "1-0":
                        winner = chess.WHITE
                    elif result == "0-1":
                        winner = chess.BLACK
                    else:
                        winner = None
                    for ply, move in enumerate(mainline_moves):
                        if ply >= MAX_PLY:
                            break
                        try:
                            k = key_hex(board)
                            pos = book.get_position(k)
                            bm = pos.get_move(move.uci())
                            bm.move = move
                            decay = max(1, (MAX_PLY - ply) // 5)
                            if winner is not None:
                                if board.turn == winner:
                                    bm.weight += 5 * decay
                                else:
                                    bm.weight += 2 * decay
                            else:
                                bm.weight += 3 * decay
                            board.push(move)
                        except Exception:
                            break
                time.sleep(0.5)
        except Exception:
            pass

    print(f"Parsed {processed} PGNs, kept {kept} games")
    book.normalize()
    for pos in book.positions.values():
        for bm in pos.moves.values():
            bm.weight = min(MAX_BOOK_WEIGHT, bm.weight + random.randint(0, 2))
    book.save_polyglot(bin_path)

    for pos_key, pos in book.positions.items():
        for bm in pos.moves.values():
            if bm.move:
                print(bm.move.uci(), bm.weight)


if __name__ == "__main__":
    build_book(BOOK_OUTPUT)
