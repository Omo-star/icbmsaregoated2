import json
import time
from datetime import datetime
import os

STATUS_FILE = "lichess_status.json"

DEFAULT_STATUS = {
    "online": False,
    "playing": False,
    "rating": "N/A",
    "opponent": "None",
    "variant": "N/A",
    "time_control": "N/A",
    "time_left": 0,
    "timestamp": None,
    "last_game": None,
    "updated": 0
}

def load_old():
    if not os.path.exists(STATUS_FILE):
        return DEFAULT_STATUS.copy()
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except:
        return DEFAULT_STATUS.copy()


def write_status(update_dict: dict):

    data = load_old()

    for k, v in update_dict.items():
        data[k] = v

    data["updated"] = time.time()

    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)
