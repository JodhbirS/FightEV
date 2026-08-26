"""
Scrape new UFC fights and upsert into the SQLite database.
Also scrapes weight classes and updates fighter profiles.

Run from repo root:  python backend/scrape_new_fights.py
"""
import os
import re
import sys
import math
import time
import urllib.parse
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Allow running from either repo root or backend/
if os.path.basename(os.getcwd()) == "backend":
    sys.path.insert(0, ".")
    DB_PATH = "data/fightev.db"
else:
    sys.path.insert(0, "backend")
    DB_PATH = "backend/data/fightev.db"

from database import Base
from models import Fighter, Fight, EloSnapshot

WIKI_HEADERS = {"User-Agent": "FightEV-Bot/1.0 (https://fightev.app; dev@fightev.app)"}


def clean_method(raw: str) -> str:
    """Strip whitespace/newline artifacts from scraped method strings."""
    return re.sub(r"\s+", " ", str(raw)).strip()


def normalise_result(raw: str) -> str:
    r = re.sub(r"\s+", " ", str(raw)).strip().lower()
    if r.startswith("draw"):
        return "draw"
    if r.startswith("nc"):
        return "nc"
    if "def" in r:
        return "win"
    return r


def normalize_wiki_method(raw: str) -> str:
    full = raw.lower()
    if "unanimous" in full:
        return "U-DEC"
    elif "split" in full:
        return "S-DEC"
    elif "majority" in full:
        return "M-DEC"
    elif "submission" in full or "sub" in full:
        match = re.search(r"\((.*?)\)", raw)
        sub_type = match.group(1).title() if match else ""
        return f"SUB {sub_type}".strip()
    elif "tko" in full or "ko" in full:
        match = re.search(r"\((.*?)\)", raw)
        ko_type = match.group(1).title() if match else ""
        return f"KO/TKO {ko_type}".strip()
    elif "decision" in full:
        return "U-DEC"
    m = re.sub(r"\(.*?\)|\[.*?\]", "", raw).strip()
    return m if m else "Decision"


def get_or_create_fighter(session, name: str, weight_class: str | None = None) -> Fighter:
    fighter = session.query(Fighter).filter(Fighter.name.ilike(name)).first()
    if fighter:
        if weight_class and not fighter.weight_class:
            fighter.weight_class = weight_class
        return fighter
    fighter = Fighter(name=name, weight_class=weight_class)
    session.add(fighter)
    session.flush()
    return fighter


def fight_exists(session, event: str, f1_id: int, f2_id: int) -> bool:
    """Check if this bout between these two fighters at this event already exists."""
    return (
        session.query(Fight)
        .filter(
            Fight.event == event,
            (
                ((Fight.fighter_1_id == f1_id) & (Fight.fighter_2_id == f2_id))
                | ((Fight.fighter_1_id == f2_id) & (Fight.fighter_2_id == f1_id))
            ),
        )
        .first()
        is not None
    )


def recompute_elo(session):
    """Recompute all Elo snapshots from scratch using round-based K-factor and inactivity decay."""
    from elo_engine import get_method_factor, apply_inactivity_decay

    session.query(EloSnapshot).delete()
    session.flush()

    fights = session.query(Fight).order_by(Fight.id.asc()).all()

    INITIAL_ELO = 1000.0
    BASE_K = 40.0
    ratings = defaultdict(lambda: INITIAL_ELO)
    bouts = defaultdict(int)
    last_fight = {}

    for idx, fight in enumerate(fights, 1):
        f1_id, f2_id = fight.fighter_1_id, fight.fighter_2_id

        # Apply mild ring rust / inactivity decay before fight
        ra = apply_inactivity_decay(ratings[f1_id], last_fight.get(f1_id), idx)
        rb = apply_inactivity_decay(ratings[f2_id], last_fight.get(f2_id), idx)

        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        result = fight.result
        if result == "win":
            sa, sb = 1.0, 0.0
            f1_r, f2_r = "win", "loss"
        elif result == "draw":
            sa, sb = 0.5, 0.5
            f1_r, f2_r = "draw", "draw"
        else:
            sa, sb = 0.0, 0.0
            f1_r, f2_r = "nc", "nc"

        mf = get_method_factor(fight.method, fight.round)
        k1 = (BASE_K / math.sqrt(max(1, bouts[f1_id]))) * mf
        k2 = (BASE_K / math.sqrt(max(1, bouts[f2_id]))) * mf

        new_ra = round(ra + k1 * (sa - ea), 2)
        new_rb = round(rb + k2 * (sb - eb), 2)

        session.add(EloSnapshot(
            fighter_id=f1_id, fight_id=fight.id,
            elo_before=ra, elo_after=new_ra,
            opponent_id=f2_id, result=f1_r,
        ))
        session.add(EloSnapshot(
            fighter_id=f2_id, fight_id=fight.id,
            elo_before=rb, elo_after=new_rb,
            opponent_id=f1_id, result=f2_r,
        ))

        ratings[f1_id] = new_ra
        ratings[f2_id] = new_rb
        last_fight[f1_id] = idx
        last_fight[f2_id] = idx
        bouts[f1_id] += 1
        bouts[f2_id] += 1

    session.flush()


def scrape_wikipedia_events(session) -> int:
    """Scrape recent completed UFC events from Wikipedia."""
    print("Checking completed UFC events on Wikipedia...")
    url = "https://en.wikipedia.org/w/api.php?action=parse&page=2026_in_UFC&prop=text&format=json"
    res = requests.get(url, headers=WIKI_HEADERS)
    if res.status_code != 200:
        return 0

    pdata = res.json()
    html = pdata.get("parse", {}).get("text", {}).get("*", "")
    soup = BeautifulSoup(html, "html.parser")

    event_links = []
    tables = soup.find_all("table", {"class": "wikitable"})
    for t in tables:
        for tr in t.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) >= 3:
                # Check if it has an event number / link
                links = tr.find_all("a")
                for a in links:
                    title = a.get("title", "")
                    if "UFC" in title and "2026" not in title and "rankings" not in title.lower() and "apex" not in title.lower():
                        href = a.get("href", "")
                        page_name = href.replace("/wiki/", "")
                        if page_name and page_name not in [x[0] for x in event_links]:
                            event_links.append((page_name, a.get_text(strip=True)))

    print(f"Found {len(event_links)} candidate events to check.")

    new_fights = 0
    # Process events in chronological order (from older to newest)
    for page_name, ev_title in reversed(event_links):
        parse_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(page_name)}&prop=text&format=json"
        try:
            r = requests.get(parse_url, headers=WIKI_HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            ev_data = r.json()
            ev_html = ev_data.get("parse", {}).get("text", {}).get("*", "")
            ev_soup = BeautifulSoup(ev_html, "html.parser")

            tables = ev_soup.find_all("table", {"class": "toccolours"}) + ev_soup.find_all("table", {"class": "wikitable"})
            event_name = ev_title.replace("_", " ")

            for t in tables:
                for tr in t.find_all("tr"):
                    tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if len(tds) >= 7 and any(sep in tds[2].lower() for sep in ["def.", "def"]):
                        wc = tds[0]
                        f1_name = re.sub(r"\(.*?\)|\[.*?\]", "", tds[1]).strip()
                        res_word = tds[2].strip()
                        f2_name = re.sub(r"\(.*?\)|\[.*?\]", "", tds[3]).strip()
                        raw_method = re.sub(r"\[.*?\]", "", tds[4]).strip()
                        rnd_str = tds[5].strip()
                        tm_str = tds[6].strip()

                        if not f1_name or not f2_name or "fighter" in f1_name.lower():
                            continue

                        result = "win" if "def" in res_word.lower() else "draw"
                        method = normalize_wiki_method(raw_method)
                        try:
                            rnd = int(rnd_str)
                        except Exception:
                            rnd = 1

                        f1 = get_or_create_fighter(session, f1_name, wc)
                        f2 = get_or_create_fighter(session, f2_name, wc)

                        if not fight_exists(session, event_name, f1.id, f2.id):
                            session.add(Fight(
                                event=event_name,
                                fighter_1_id=f1.id,
                                fighter_2_id=f2.id,
                                result=result,
                                method=method,
                                round=rnd,
                                time=tm_str,
                            ))
                            new_fights += 1
                            print(f"  + Added fight: {event_name} | {f1_name} def. {f2_name} ({method})")

            time.sleep(0.3)
        except Exception as e:
            print(f"Error parsing event {page_name}: {e}")

    return new_fights


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    new_fights = scrape_wikipedia_events(session)

    if new_fights > 0:
        session.flush()
        print(f"Added {new_fights} new fights. Recomputing Elo ratings...")
        recompute_elo(session)
        session.commit()
        print(f"Successfully updated database with {new_fights} new fights!")
    else:
        session.commit()
        print("Database is already up-to-date with all recent UFC events.")


if __name__ == "__main__":
    main()
