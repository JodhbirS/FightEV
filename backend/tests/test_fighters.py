"""
Tests for the /fighters endpoints.

Uses an in-memory SQLite database with a small fixture dataset.
"""
import math
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from models import Fighter, Fight, EloSnapshot
from main import app

# --- Test DB setup ---

TEST_DATABASE_URL = "sqlite:///./test_fightev.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables and seed test data once for the module."""
    Base.metadata.create_all(bind=test_engine)
    db = TestSession()

    # Create fighters
    f1 = Fighter(name="Jon Jones", weight_class="Light Heavyweight")
    f2 = Fighter(name="Alexander Gustafsson")
    f3 = Fighter(name="Daniel Cormier", weight_class="Heavyweight")
    db.add_all([f1, f2, f3])
    db.flush()

    # Create fights (chronological order by ID)
    fight1 = Fight(
        event="UFC 165",
        fighter_1_id=f1.id,
        fighter_2_id=f2.id,
        result="win",
        method="U-DEC",
        round=5,
        time="5:00",
    )
    fight2 = Fight(
        event="UFC 182",
        fighter_1_id=f1.id,
        fighter_2_id=f3.id,
        result="win",
        method="U-DEC",
        round=5,
        time="5:00",
    )
    fight3 = Fight(
        event="UFC 214",
        fighter_1_id=f3.id,
        fighter_2_id=f1.id,
        result="win",
        method="KO/TKO Punches",
        round=2,
        time="3:01",
    )
    db.add_all([fight1, fight2, fight3])
    db.flush()

    # Compute Elo snapshots
    INITIAL_ELO = 1000.0
    BASE_K = 40.0
    METHOD_BOOST = 1.15
    ratings = defaultdict(lambda: INITIAL_ELO)
    bouts = defaultdict(int)

    for fight, f1_id, f2_id, result, method in [
        (fight1, f1.id, f2.id, "win", "U-DEC"),
        (fight2, f1.id, f3.id, "win", "U-DEC"),
        (fight3, f3.id, f1.id, "win", "KO/TKO Punches"),
    ]:
        ra = ratings[f1_id]
        rb = ratings[f2_id]
        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        sa, sb = (1.0, 0.0) if result == "win" else (0.5, 0.5)

        m = method.upper()
        k1 = BASE_K / math.sqrt(max(1, bouts[f1_id]))
        k2 = BASE_K / math.sqrt(max(1, bouts[f2_id]))
        if "KO" in m or "SUB" in m:
            k1 *= METHOD_BOOST
            k2 *= METHOD_BOOST

        new_ra = round(ra + k1 * (sa - ea), 2)
        new_rb = round(rb + k2 * (sb - eb), 2)

        f1_result = "win" if result == "win" else "draw"
        f2_result = "loss" if result == "win" else "draw"

        db.add(EloSnapshot(
            fighter_id=f1_id, fight_id=fight.id,
            elo_before=ra, elo_after=new_ra,
            opponent_id=f2_id, result=f1_result,
        ))
        db.add(EloSnapshot(
            fighter_id=f2_id, fight_id=fight.id,
            elo_before=rb, elo_after=new_rb,
            opponent_id=f1_id, result=f2_result,
        ))

        ratings[f1_id] = new_ra
        ratings[f2_id] = new_rb
        bouts[f1_id] += 1
        bouts[f2_id] += 1

    db.commit()
    yield
    db.close()
    Base.metadata.drop_all(bind=test_engine)
    import os
    if os.path.exists("./test_fightev.db"):
        os.remove("./test_fightev.db")


client = TestClient(app)


# --- Tests ---

class TestGetFighters:
    def test_paginated_default(self):
        """GET /fighters returns paginated results with correct structure."""
        resp = client.get("/fighters")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "fighters" in data
        assert data["total"] == 3
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert len(data["fighters"]) == 3

    def test_paginated_with_limit(self):
        """GET /fighters?limit=1 returns exactly 1 fighter."""
        resp = client.get("/fighters?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fighters"]) == 1
        assert data["total"] == 3

    def test_paginated_with_offset(self):
        """GET /fighters?offset=1&limit=1 skips the first fighter."""
        resp1 = client.get("/fighters?limit=3")
        all_names = [f["name"] for f in resp1.json()["fighters"]]

        resp2 = client.get("/fighters?offset=1&limit=1")
        data = resp2.json()
        assert data["fighters"][0]["name"] == all_names[1]

    def test_search_filter(self):
        """GET /fighters?search=jones returns matching fighters."""
        resp = client.get("/fighters?search=jones")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any("Jones" in f["name"] for f in data["fighters"])

    def test_division_filter(self):
        """GET /fighters?division=Heavyweight returns matching division fighters."""
        resp = client.get("/fighters?division=Heavyweight")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert all("Heavyweight" in (f["weight_class"] or "") for f in data["fighters"])

    def test_fighter_has_elo(self):
        """Each fighter in the list has a numeric current_elo."""
        resp = client.get("/fighters")
        for f in resp.json()["fighters"]:
            assert isinstance(f["current_elo"], (int, float))
            assert f["current_elo"] != 0


class TestGetFighterDetail:
    def test_happy_path(self):
        """GET /fighters/{id} returns full fighter detail."""
        # Get a valid ID first
        resp = client.get("/fighters?limit=1")
        fighter_id = resp.json()["fighters"][0]["id"]

        resp2 = client.get(f"/fighters/{fighter_id}")
        assert resp2.status_code == 200
        data = resp2.json()

        assert "id" in data
        assert "name" in data
        assert "current_elo" in data
        assert "total_fights" in data
        assert "wins" in data
        assert "losses" in data
        assert "draws" in data
        assert "fight_history" in data
        assert "elo_history" in data
        assert len(data["elo_history"]) > 0

    def test_elo_history_structure(self):
        """Elo history entries have correct fields."""
        resp = client.get("/fighters?limit=1")
        fighter_id = resp.json()["fighters"][0]["id"]

        resp2 = client.get(f"/fighters/{fighter_id}")
        elo_point = resp2.json()["elo_history"][0]

        assert "fight_id" in elo_point
        assert "fight_sequence" in elo_point
        assert "elo_after" in elo_point
        assert "opponent_name" in elo_point
        assert "result" in elo_point
        assert "event" in elo_point

    def test_not_found(self):
        """GET /fighters/999999 returns 404."""
        resp = client.get("/fighters/999999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Fighter not found"

    def test_by_name_happy_path(self):
        """GET /fighters/by-name/{name} returns fighter detail."""
        resp = client.get("/fighters/by-name/Jon%20Jones")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Jon Jones"
        assert len(data["fight_history"]) > 0

    def test_by_name_not_found(self):
        """GET /fighters/by-name/{invalid_name} returns 404."""
        resp = client.get("/fighters/by-name/NonExistentFighter999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Fighter not found"
