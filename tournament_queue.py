import json
import os
import datetime

TOURNAMENT_FILE = "tournaments.json"


def _log(msg: str):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[TournamentQueue {ts}] {msg}")


def _load_raw():
    if not os.path.exists(TOURNAMENT_FILE):
        _log("No queue file found — creating new structure.")
        return {"pending": []}

    try:
        with open(TOURNAMENT_FILE, "r") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            _log("Corrupt queue file: expected dict. Resetting.")
            return {"pending": []}

        if "pending" not in data or not isinstance(data["pending"], list):
            _log("Queue missing 'pending' list. Resetting list.")
            data["pending"] = []

        return data

    except Exception as e:
        _log(f"Error loading queue file: {e}. Resetting.")
        return {"pending": []}


def _save_raw(data):
    try:
        with open(TOURNAMENT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        _log("Queue saved successfully.")
    except Exception as e:
        _log(f"Error saving queue: {e}")


def add_tournament(tid: str, team: str | None = None):
    data = _load_raw()

    entry = {"id": tid, "team": team}

    existing_ids = [e["id"] for e in data["pending"]]

    if tid not in existing_ids:
        data["pending"].append(entry)
        _save_raw(data)
        _log(f"Added tournament {tid} (team={team})")
    else:
        _log(f"Tournament {tid} already exists; skipping.")


def get_pending():
    data = _load_raw()
    _log(f"Loaded pending list: {data['pending']}")
    return list(data["pending"])


def mark_processed(tid: str):
    data = _load_raw()
    
    before = len(data["pending"])
    data["pending"] = [e for e in data["pending"] if e["id"] != tid]
    after = len(data["pending"])

    _save_raw(data)
    removed = before - after

    if removed > 0:
        _log(f"Marked {tid} as processed — removed {removed} entry.")
    else:
        _log(f"Attempted to process {tid}, but it was not in queue.")
