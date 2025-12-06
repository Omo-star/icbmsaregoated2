import json
import os

TOURNAMENT_FILE = "tournaments.json"


def _load_raw():
    if not os.path.exists(TOURNAMENT_FILE):
        return {"pending": []}
    try:
        with open(TOURNAMENT_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"pending": []}
        if "pending" not in data or not isinstance(data["pending"], list):
            data["pending"] = []
        return data
    except:
        return {"pending": []}


def _save_raw(data):
    with open(TOURNAMENT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_tournament(tid: str, team: str | None = None):
    data = _load_raw()

    entry = {"id": tid, "team": team}

    if entry not in data["pending"]:
        data["pending"].append(entry)
        _save_raw(data)
        print(f"[TournamentQueue] Added tournament {tid} (team={team})")
    else:
        print(f"[TournamentQueue] Tournament {tid} (team={team}) already in queue")



def get_pending():
    data = _load_raw()
    return list(data["pending"])


def mark_processed(tid: str):
    data = _load_raw()
    if tid in data["pending"]:
        data["pending"].remove(tid)
        _save_raw(data)
        print(f"[TournamentQueue] Marked {tid} as processed")
