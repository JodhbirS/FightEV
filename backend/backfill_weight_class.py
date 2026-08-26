"""
Backfill weight_class for all fighters in the DB via Wikipedia batch API.
Sends up to 50 fighter names per request — should complete in ~60-90 seconds.

Run from repo root:
    python backend/backfill_weight_class.py
"""
import os
import re
import sys
import time

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

if os.path.basename(os.getcwd()) == "backend":
    sys.path.insert(0, ".")
    DB_PATH = "data/fightev.db"
else:
    sys.path.insert(0, "backend")
    DB_PATH = "backend/data/fightev.db"

from database import Base
from models import Fighter

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "FightEV/1.0 (contact@fightev.app)"}
BATCH_SIZE = 50

# Weight classes ordered from heaviest to lightest so we try to pick the
# highest / most recent class when a fighter has competed at multiple.
WEIGHT_CLASSES_ORDERED = [
    "Heavyweight",
    "Light Heavyweight",
    "Middleweight",
    "Welterweight",
    "Lightweight",
    "Featherweight",
    "Bantamweight",
    "Flyweight",
    "Women's Featherweight",
    "Women's Bantamweight",
    "Women's Flyweight",
    "Women's Strawweight",
    "Strawweight",
    "Catch Weight",
]

# Map lower-case variants to canonical strings
WEIGHT_MAP = {wc.lower(): wc for wc in WEIGHT_CLASSES_ORDERED}


def extract_weight_class(text: str) -> str | None:
    """Parse most prominent weight class from Wikipedia intro text."""
    text_lower = text.lower()
    # Walk from Heavyweight downward — return the FIRST match found.
    # This biases toward the highest weight class in the text, which is
    # usually the most recent (e.g. Jon Jones → Heavyweight).
    for wc_lower, wc_canonical in WEIGHT_MAP.items():
        if wc_lower in text_lower:
            return wc_canonical
    return None


def wiki_batch(names: list[str]) -> dict[str, str]:
    """Fetch Wikipedia intro extracts for up to BATCH_SIZE fighters.
    Returns {name: weight_class} for those with a match."""
    titles = "|".join(n.replace(" ", "_") for n in names)
    try:
        r = requests.get(
            WIKI_API,
            params={
                "action": "query",
                "titles": titles,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "format": "json",
                "redirects": 1,
            },
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"    Wiki API error: {e}")
        return {}

    data = r.json()
    # Build a normalised-title -> weight_class map
    wc_map: dict[str, str] = {}

    pages = data.get("query", {}).get("pages", {})
    redirects = {
        r["from"].replace("_", " "): r["to"].replace("_", " ")
        for r in data.get("query", {}).get("redirects", [])
    }

    for page in pages.values():
        if page.get("missing") is not None:
            continue
        page_title = page.get("title", "").replace("_", " ")
        extract = page.get("extract", "")
        wc = extract_weight_class(extract)
        if wc:
            wc_map[page_title] = wc

    # Map back from original names
    result: dict[str, str] = {}
    for name in names:
        # Try direct match
        if name in wc_map:
            result[name] = wc_map[name]
            continue
        # Try redirect chain
        redirected = redirects.get(name)
        if redirected and redirected in wc_map:
            result[name] = wc_map[redirected]

    return result


def main():
    engine = create_engine(
        f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    fighters = (
        session.query(Fighter)
        .filter((Fighter.weight_class == None) | (Fighter.weight_class == ""))
        .all()
    )
    print(f"Fighters missing weight class: {len(fighters)}")

    if not fighters:
        print("All fighters already have a weight class.")
        return

    name_to_fighter = {f.name: f for f in fighters}
    names = list(name_to_fighter.keys())

    total_updated = 0
    for batch_start in range(0, len(names), BATCH_SIZE):
        batch = names[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(names) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} fighters)...", end=" ", flush=True)

        wc_results = wiki_batch(batch)
        updated = 0
        for name, wc in wc_results.items():
            if name in name_to_fighter:
                name_to_fighter[name].weight_class = wc
                updated += 1
                total_updated += 1

        print(f"{updated} matched")

        # Commit every 5 batches to avoid losing too much on error
        if batch_num % 5 == 0:
            session.commit()
            print(f"  [checkpoint] {total_updated} updated so far")

        time.sleep(0.5)  # be polite to Wikipedia

    session.commit()
    print(f"\nDone. Updated {total_updated} out of {len(fighters)} fighters.")

    still_missing = (
        session.query(Fighter)
        .filter((Fighter.weight_class == None) | (Fighter.weight_class == ""))
        .count()
    )
    print(f"Still missing: {still_missing} (likely retired fighters with no Wikipedia page)")


if __name__ == "__main__":
    main()
