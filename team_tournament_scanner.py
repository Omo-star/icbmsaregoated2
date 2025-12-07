import asyncio
import aiohttp
import datetime
import re
from bs4 import BeautifulSoup
from tournament_queue import add_tournament

TEAM = "darkonbot"
SEEN = set()
JOIN_WINDOW_SECONDS = 300

def _log(msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RTTeamScanner {ts}] {msg}")

def parse_time_from_infos_cell(info_td):
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

    _log(f"  RAW infos cell text: {repr(info_td.text)}")

    time_tag = info_td.find("time")
    if time_tag:
        _log(f"  Found <time> tag with datetime={time_tag.get('datetime')}")
    if time_tag and time_tag.has_attr("datetime"):
        try:
            iso = time_tag["datetime"].replace("Z", "+00:00")
            parsed = datetime.datetime.fromisoformat(iso)
            _log(f"  Parsed ISO time -> {parsed}")
            return parsed
        except Exception as e:
            _log(f"  Failed ISO parse: {e}")

    lines = [l.strip() for l in info_td.text.split("\n") if l.strip()]
    _log(f"  Parsed lines from infos cell: {lines}")

    if len(lines) < 2:
        _log("  Not enough lines to parse time")
        return None

    t = lines[1].lower()
    _log(f"  Interpreting time string: {t}")

    if t == "playing right now":
        _log("  Detected LIVE tournament")
        return now

    m = re.match(r"in (\d+) minutes?", t)
    if m:
        mins = int(m.group(1))
        _log(f"  Parsed relative time: in {mins} minutes")
        return now + datetime.timedelta(minutes=mins)

    m = re.match(r"in (\d+) hours?", t)
    if m:
        hrs = int(m.group(1))
        _log(f"  Parsed relative time: in {hrs} hours")
        return now + datetime.timedelta(hours=hrs)

    try:
        dt = datetime.datetime.strptime(lines[1], "%b %d, %Y, %I:%M %p")
        parsed = dt.replace(tzinfo=datetime.timezone.utc)
        _log(f"  Parsed absolute datetime: {parsed}")
        return parsed
    except Exception as e:
        _log(f"  Failed to parse datetime: {e}")

    return None

async def fetch_team_tournaments_html(session):
    url = f"https://lichess.org/team/{TEAM}/tournaments"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}

    _log(f"Fetching HTML: {url}")

    try:
        async with session.get(url, headers=headers) as r:
            body = await r.text()
            _log(f"Received HTTP {r.status}, first 300 chars:\n{body[:300].replace(chr(10),' ')}")

            if r.status != 200:
                return []

            soup = BeautifulSoup(body, "html.parser")

            container = soup.find("div", class_="team-tournaments__next")
            if not container:
                _log("Did NOT find .team-tournaments__next div")
                return []

            rows = container.find_all("tr", class_=lambda c: c and "enterable" in c)
            _log(f"Found {len(rows)} <tr> rows with 'enterable' class")

            now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            found = []

            for row in rows:
                _log(f"Processing <tr class='{row.get('class')}'>")

                link = row.find("a", href=True)
                if not link:
                    _log("  No <a> link in row — skipping")
                    continue

                href = link["href"]
                _log(f"  Found link href={href}")

                m = re.match(r"^/tournament/([A-Za-z0-9]{8,12})$", href)
                if not m:
                    _log("  Href did NOT match expected /tournament/<ID> format — skipping")
                    continue

                tid = m.group(1)
                _log(f"  Tournament ID={tid}")

                info_td = row.find("td", class_="infos")
                if not info_td:
                    _log("  No <td class='infos'> — skipping")
                    continue

                start_time = parse_time_from_infos_cell(info_td)
                if not start_time:
                    _log("  Could NOT parse start time — skipping")
                    continue

                delta = (start_time - now).total_seconds()
                _log(f"  start_time={start_time}, delta={delta}s")

                if delta <= JOIN_WINDOW_SECONDS:
                    _log(f"  -> JOINABLE: within {JOIN_WINDOW_SECONDS}s window")
                    found.append(tid)
                else:
                    _log("  -> NOT joinable yet")

            _log(f"FINAL joinable tournaments: {found}")
            return found

    except Exception as e:
        _log(f"Error scraping tournaments: {e}")
        return []

async def realtime_team_scanner(_, interval=30):
    _log("Started real-time team scanner")
    async with aiohttp.ClientSession() as session:
        while True:
            if len(SEEN) > 300:
                SEEN.clear()

            tournaments = await fetch_team_tournaments_html(session)

            if not tournaments:
                _log("No tournaments within join window")
                await asyncio.sleep(interval)
                continue

            _log(f"Joinable tournaments: {tournaments}")

            for tid in tournaments:
                if tid in SEEN:
                    _log(f"Skipping {tid} (already seen)")
                    continue
                add_tournament(tid, TEAM)
                _log(f"JOIN NOW {tid}")
                SEEN.add(tid)

            await asyncio.sleep(interval)

async def team_tournament_loop(token):
    await realtime_team_scanner(token, interval=30)
