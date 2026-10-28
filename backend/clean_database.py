"""Repair and normalize the committed UFC database."""

import re
import sys
import unicodedata
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup
from sqlalchemy import inspect, text

sys.path.insert(0, ".")
from database import SessionLocal, engine  # noqa: E402
from models import Fighter, Fight  # noqa: E402

HEADERS = {"User-Agent": "FightEV-Bot/1.0 (https://fightev.app)"}


def normalize_event(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", name.lower())


def fetch_event_dates() -> dict[str, date]:
    response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "parse", "page": "List of UFC events", "prop": "text", "format": "json"},
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.json()["parse"]["text"]["*"], "html.parser")
    result = {}
    for table in soup.find_all("table", class_="wikitable"):
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if len(cells) < 2 or cells[0] in {"Event", "#", "Year"}:
                continue
            event_name, raw_date = cells[0], cells[1]
            if cells[0].isdigit() and len(cells) >= 3:
                event_name, raw_date = cells[1], cells[2]
            try:
                event_date = datetime.strptime(
                    re.sub(r"\[.*?\]", "", raw_date).strip(), "%b %d, %Y"
                ).date()
            except ValueError:
                continue
            normalized = normalize_event(event_name)
            result[normalized] = event_date
            numbered_event = re.match(r"(ufc\d+)", normalized)
            if numbered_event:
                result.setdefault(numbered_event.group(1), event_date)
    return result


def add_event_date_column() -> None:
    with engine.begin() as connection:
        if not any(column["name"] == "event_date" for column in inspect(engine).get_columns("fights")):
            connection.execute(text("ALTER TABLE fights ADD COLUMN event_date DATE"))
        connection.execute(text("DROP TABLE IF EXISTS elo_snapshots"))


def merge_renamed_fighters(db) -> int:
    """Merge known fighter renames before checking for duplicate bouts."""
    canonical = db.query(Fighter).filter(Fighter.name == "King Green").first()
    legacy = db.query(Fighter).filter(Fighter.name == "Bobby Green").first()
    if not canonical or not legacy:
        return 0

    db.query(Fight).filter(Fight.fighter_1_id == legacy.id).update(
        {Fight.fighter_1_id: canonical.id}, synchronize_session=False
    )
    db.query(Fight).filter(Fight.fighter_2_id == legacy.id).update(
        {Fight.fighter_2_id: canonical.id}, synchronize_session=False
    )
    db.delete(legacy)
    db.flush()
    return 1


def main() -> None:
    add_event_date_column()
    dates = fetch_event_dates()
    db = SessionLocal()
    try:
        merged = merge_renamed_fighters(db)
        seen = set()
        removed = 0
        for fight in db.query(Fight).all():
            fighter_1 = db.get(Fighter, fight.fighter_1_id)
            fighter_2 = db.get(Fighter, fight.fighter_2_id)
            key = (
                fight.event.lower(),
                min(fight.fighter_1_id, fight.fighter_2_id),
                max(fight.fighter_1_id, fight.fighter_2_id),
            )
            invalid = (
                not fighter_1
                or not fighter_2
                or fight.fighter_1_id == fight.fighter_2_id
                or re.fullmatch(r"\d{4} in ufc", fight.event.lower())
                or "road to ufc" in fight.event.lower()
                or "defeats" in f"{fighter_1.name} {fighter_2.name}".lower()
                or key in seen
            )
            if invalid:
                db.delete(fight)
                removed += 1
                continue
            seen.add(key)
            normalized_event = normalize_event(fight.event)
            numbered_event = re.match(r"(ufc\d+)", normalized_event)
            fight.event_date = dates.get(normalized_event)
            if fight.event_date is None and numbered_event:
                fight.event_date = dates.get(numbered_event.group(1))

        db.flush()
        db.commit()
        dated = db.query(Fight).filter(Fight.event_date.is_not(None)).count()
        print(f"Merged {merged} renamed fighter; removed {removed} invalid/duplicate fights; dated {dated} fights.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
