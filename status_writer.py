import json, time

def write_status(data):
    data["updated"] = time.time()
    with open("lichess_status.json", "w") as f:
        json.dump(data, f, indent=2)
