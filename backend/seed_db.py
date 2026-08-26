"""
One-time migration script: reads the existing CSV and populates the SQLite
database with fighters, fights, and elo_snapshots.

Run from repo root:  python backend/seed_db.py
Run from backend/:   python seed_db.py
"""
import os
import re
import sys
import math
from collections import defaultdict

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Allow running from either repo root or backend/
if os.path.basename(os.getcwd()) == "backend":
    sys.path.insert(0, ".")
    CSV_PATH = "data/ufcfights.csv"
    DB_PATH = "data/fightev.db"
else:
    sys.path.insert(0, "backend")
    CSV_PATH = "backend/data/ufcfights.csv"
    DB_PATH = "backend/data/fightev.db"

from database import Base
from models import Fighter, Fight, EloSnapshot


def clean_method(raw: str) -> str:
    """Strip whitespace/newline artifacts from scraped method strings."""
    return re.sub(r"\s+", " ", str(raw)).strip()


def normalise_result(raw: str) -> str:
    """Normalise result strings that have whitespace artefacts."""
    r = re.sub(r"\s+", " ", str(raw)).strip().lower()
    if r.startswith("draw"):
        return "draw"
    if r.startswith("nc"):
        return "nc"
    return r  # "win"


def seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # Remove old DB so we start fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # ---- Load CSV ----
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} rows from {CSV_PATH}")

    # ---- Build fighter lookup ----
    fighter_names = set(df["fighter_1"].unique()) | set(df["fighter_2"].unique())
    name_to_fighter = {}
    for name in sorted(fighter_names):
        f = Fighter(name=name)
        session.add(f)
        name_to_fighter[name] = f
    session.flush()  # assigns IDs
    print(f"Created {len(name_to_fighter)} fighters")

    # ---- Insert fights (chronological = reversed CSV order, oldest first) ----
    fights_added = 0
    fight_objects = []  # keep ordered list for Elo processing
    for _, row in df.iloc[::-1].iterrows():
        f1 = name_to_fighter[row["fighter_1"]]
        f2 = name_to_fighter[row["fighter_2"]]
        result = normalise_result(row["result"])
        method = clean_method(row["method"])

        fight = Fight(
            event=row["event"],
            fighter_1_id=f1.id,
            fighter_2_id=f2.id,
            result=result,
            method=method,
            round=int(row["round"]),
            time=str(row["time"]),
        )
        session.add(fight)
        fight_objects.append((fight, f1, f2, result, method))
        fights_added += 1

    session.flush()
    print(f"Inserted {fights_added} fights")

    # ---- Compute Elo and write snapshots ----
    INITIAL_ELO = 1000.0
    BASE_K = 40.0
    METHOD_BOOST = 1.15

    ratings: dict[int, float] = defaultdict(lambda: INITIAL_ELO)
    bouts: dict[int, int] = defaultdict(int)
    snapshots_added = 0

    for fight, f1, f2, result, method in fight_objects:
        ra = ratings[f1.id]
        rb = ratings[f2.id]
        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        if result == "win":
            sa, sb = 1.0, 0.0
        elif result == "draw":
            sa, sb = 0.5, 0.5
        else:
            sa, sb = 0.0, 0.0

        m = method.upper()
        k1 = BASE_K / math.sqrt(max(1, bouts[f1.id]))
        k2 = BASE_K / math.sqrt(max(1, bouts[f2.id]))
        if "KO" in m or "SUB" in m:
            k1 *= METHOD_BOOST
            k2 *= METHOD_BOOST

        new_ra = round(ra + k1 * (sa - ea), 2)
        new_rb = round(rb + k2 * (sb - eb), 2)

        # Fighter 1 snapshot
        if result == "win":
            f1_result = "win"
            f2_result = "loss"
        elif result == "draw":
            f1_result = "draw"
            f2_result = "draw"
        else:
            f1_result = "nc"
            f2_result = "nc"

        session.add(EloSnapshot(
            fighter_id=f1.id,
            fight_id=fight.id,
            elo_before=ra,
            elo_after=new_ra,
            opponent_id=f2.id,
            result=f1_result,
        ))
        session.add(EloSnapshot(
            fighter_id=f2.id,
            fight_id=fight.id,
            elo_before=rb,
            elo_after=new_rb,
            opponent_id=f1.id,
            result=f2_result,
        ))
        snapshots_added += 2

        ratings[f1.id] = new_ra
        ratings[f2.id] = new_rb
        bouts[f1.id] += 1
        bouts[f2.id] += 1

    session.commit()
    print(f"Created {snapshots_added} Elo snapshots")
    print(f"Database seeded at {DB_PATH}")


if __name__ == "__main__":
    seed()
