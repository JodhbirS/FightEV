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
from models import Fighter, Fight

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


def normalize_name(s: str) -> str:
    if not s:
        return ""
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = re.sub(r"[\'\".\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def get_or_create_fighter(session, name: str, weight_class: str | None = None) -> Fighter:
    # 1. Exact case-insensitive match
    fighter = session.query(Fighter).filter(Fighter.name.ilike(name)).first()
    if fighter:
        if weight_class and not fighter.weight_class:
            fighter.weight_class = weight_class
        return fighter

    # 2. Normalized name match (accents, hyphens, punctuation)
    norm = normalize_name(name)
    all_fighters = session.query(Fighter).all()
    for f in all_fighters:
        if normalize_name(f.name) == norm:
            if weight_class and not f.weight_class:
                f.weight_class = weight_class
            return f

    fighter = Fighter(name=name, weight_class=weight_class)
    session.add(fighter)
    session.flush()
    return fighter


def extract_event_core(name: str) -> str:
    name_clean = re.sub(r"\(.*?\)|\[.*?\]", "", name).strip().lower()
    name_clean = re.sub(r"ufc\s*(?:fight\s*night|on\s*(?:espn|fox|fuel\s*tv|fx|abc))", "ufc_fn", name_clean)
    m = re.search(r"(ufc_fn\s*\d+|ufc\s*\d+)", name_clean)
    if m:
        return re.sub(r"\s+", " ", m.group(1))
    return name_clean.split(":")[0].strip()


def fight_exists(session, event: str, f1_id: int, f2_id: int) -> bool:
    """Check if this bout between these two fighters at this event already exists."""
    existing = (
        session.query(Fight)
        .filter(
            ((Fight.fighter_1_id == f1_id) & (Fight.fighter_2_id == f2_id))
            | ((Fight.fighter_1_id == f2_id) & (Fight.fighter_2_id == f1_id))
        )
        .all()
    )
    if not existing:
        return False

    target_core = extract_event_core(event)
    for f in existing:
        if extract_event_core(f.event) == target_core or f.event.lower() == event.lower():
            return True
    return False


def is_valid_ufc_event(event: str, fighter_1: str, fighter_2: str) -> bool:
    event_lower = event.lower()
    fighter_text = f"{fighter_1} {fighter_2}".lower()
    return not (
        re.fullmatch(r"\d{4} in ufc", event_lower)
        or "road to ufc" in event_lower
        or "defeats" in fighter_text
        or "ufc " in fighter_text
    )


def scrape_wikipedia_events(session) -> int:
    """Scrape recent completed UFC events from Wikipedia with full redirect following."""
    print("Collecting candidate UFC events from Wikipedia...")
    event_pages = []

    for source_page in ["2026_in_UFC", "List_of_UFC_events"]:
        url = f"https://en.wikipedia.org/w/api.php?action=parse&page={source_page}&prop=text&format=json&redirects=1"
        try:
            res = requests.get(url, headers=WIKI_HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            pdata = res.json()
            html = pdata.get("parse", {}).get("text", {}).get("*", "")
            soup = BeautifulSoup(html, "html.parser")

            tables = soup.find_all("table", {"class": "wikitable"})
            for t in tables:
                for tr in t.find_all("tr"):
                    for a in tr.find_all("a"):
                        title = a.get("title", "")
                        href = a.get("href", "")
                        title_lower = title.lower()
                        href_lower = href.lower()
                        if (
                            "ufc" in title_lower
                            and "rankings" not in title_lower
                            and "apex" not in title_lower
                            and "list" not in title_lower
                            and "in ufc" not in title_lower
                            and "in_ufc" not in href_lower
                            and "in mma" not in title_lower
                            and "in_mma" not in href_lower
                        ):
                            page_name = href.replace("/wiki/", "")
                            text = a.get_text(strip=True)
                            if page_name and (page_name, text) not in event_pages:
                                event_pages.append((page_name, text))
        except Exception as e:
            print(f"Error fetching {source_page}: {e}")

    print(f"Checking {len(event_pages)} candidate event pages for new/missing fights...")

    new_fights = 0
    # Process events in chronological order (from older to newest)
    for page_name, ev_title in reversed(event_pages):
        parse_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(page_name)}&prop=text&format=json&redirects=1"
        try:
            r = requests.get(parse_url, headers=WIKI_HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            ev_data = r.json()
            real_title = ev_data.get("parse", {}).get("title", ev_title)
            ev_html = ev_data.get("parse", {}).get("text", {}).get("*", "")
            ev_soup = BeautifulSoup(ev_html, "html.parser")

            tables = ev_soup.find_all("table", {"class": "toccolours"}) + ev_soup.find_all("table", {"class": "wikitable"})
            event_name = real_title.replace("_", " ")

            for t in tables:
                for tr in t.find_all("tr"):
                    tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if len(tds) >= 7 and any(sep in tds[2].lower() for sep in ["def.", "def", "vs.", "vs"]):
                        wc = tds[0]
                        f1_name = re.sub(r"\(.*?\)|\[.*?\]", "", tds[1]).strip()
                        res_word = tds[2].strip().lower()
                        f2_name = re.sub(r"\(.*?\)|\[.*?\]", "", tds[3]).strip()
                        raw_method = re.sub(r"\[.*?\]", "", tds[4]).strip()
                        rnd_str = tds[5].strip()
                        tm_str = tds[6].strip()

                        if (
                            not f1_name
                            or not f2_name
                            or "fighter" in f1_name.lower()
                            or "weight" in f1_name.lower()
                            or not is_valid_ufc_event(event_name, f1_name, f2_name)
                        ):
                            continue

                        # Check if it has a completed result
                        if not raw_method or raw_method == "—" or "tba" in raw_method.lower():
                            continue

                        if "def" in res_word:
                            result = "win"
                        elif "draw" in raw_method.lower() or "draw" in res_word:
                            result = "draw"
                        elif "nc" in raw_method.lower() or "no contest" in raw_method.lower():
                            result = "nc"
                        else:
                            result = "win"

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
                            print(f"  + Added fight: {event_name} | {f1_name} def. {f2_name} ({method}) R{rnd} {tm_str}")

            time.sleep(0.15)
        except Exception as e:
            pass

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
        print(f"Added {new_fights} new fights. The ensemble retrains on API startup.")
        recompute_elo(session)
        session.commit()
        print(f"Successfully updated database with {new_fights} new fights!")
    else:
        session.commit()
        print("Database is already up-to-date with all recent UFC events.")


if __name__ == "__main__":
    main()
