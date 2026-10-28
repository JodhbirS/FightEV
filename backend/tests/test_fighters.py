"""
Tests for the /fighters endpoints.

Uses an in-memory SQLite database with a small fixture dataset.
"""
import math
from collections import defaultdict
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from models import Fighter, Fight
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
        event_date=date.today(),
        fighter_1_id=f1.id,
        fighter_2_id=f2.id,
        result="win",
        method="U-DEC",
        round=5,
        time="5:00",
    )
    fight2 = Fight(
        event="UFC 182",
        event_date=date.today(),
        fighter_1_id=f1.id,
        fighter_2_id=f3.id,
        result="win",
        method="U-DEC",
        round=5,
        time="5:00",
    )
    fight3 = Fight(
        event="UFC 214",
        event_date=date.today(),
        fighter_1_id=f3.id,
        fighter_2_id=f1.id,
        result="win",
        method="KO/TKO Punches",
        round=2,
        time="3:01",
    )
    db.add_all([fight1, fight2, fight3])
    db.flush()
    extra_fights = [
        Fight(
            event="UFC 220",
            event_date=date.today(),
            fighter_1_id=f2.id,
            fighter_2_id=f3.id,
            result="win",
            method="U-DEC",
            round=3,
            time="5:00",
        ),
        Fight(
            event="UFC 225",
            event_date=date.today(),
            fighter_1_id=f1.id,
            fighter_2_id=f2.id,
            result="win",
            method="U-DEC",
            round=3,
            time="5:00",
        ),
        Fight(
            event="UFC 226",
            event_date=date.today(),
            fighter_1_id=f3.id,
            fighter_2_id=f1.id,
            result="win",
            method="U-DEC",
            round=3,
            time="5:00",
        ),
        Fight(
            event="UFC 227",
            event_date=date.today(),
            fighter_1_id=f2.id,
            fighter_2_id=f3.id,
            result="win",
            method="U-DEC",
            round=3,
            time="5:00",
        ),
        Fight(
            event="UFC 228",
            event_date=date.today(),
            fighter_1_id=f1.id,
            fighter_2_id=f3.id,
            result="win",
            method="U-DEC",
            round=3,
            time="5:00",
        ),
    ]
    db.add_all(extra_fights)
    db.flush()

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
    def test_returns_top_fighters_by_division(self):
        """GET /fighters returns fixed UFC division groups."""
        resp = client.get("/fighters")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "divisions" in data
        assert data["total"] == 2
        assert len(data["divisions"]) == 11
        assert all(len(group["fighters"]) <= 5 for group in data["divisions"])
        assert all(group["name"] in {
            "Flyweight", "Bantamweight", "Featherweight", "Lightweight",
            "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight",
            "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight",
        } for group in data["divisions"])

    def test_fighter_has_model_score(self):
        """Each fighter in the list has a numeric model score."""
        resp = client.get("/fighters")
        for group in resp.json()["divisions"]:
            for fighter in group["fighters"]:
                assert isinstance(fighter["model_score"], (int, float))
                assert 0 <= fighter["model_score"] <= 100


class TestGetFighterDetail:
    def test_happy_path(self):
        """GET /fighters/{id} returns full fighter detail."""
        # Get a valid ID first
        resp = client.get("/fighters")
        fighter_id = next(
            group["fighters"][0]["id"]
            for group in resp.json()["divisions"]
            if group["fighters"]
        )

        resp2 = client.get(f"/fighters/{fighter_id}")
        assert resp2.status_code == 200
        data = resp2.json()

        assert "id" in data
        assert "name" in data
        assert "model_score" in data
        assert "total_fights" in data
        assert "wins" in data
        assert "losses" in data
        assert "draws" in data
        assert "fight_history" in data
        assert "model_history" in data
        assert len(data["model_history"]) > 0

    def test_model_history_structure(self):
        """Model history entries have correct fields."""
        resp = client.get("/fighters")
        fighter_id = next(
            group["fighters"][0]["id"]
            for group in resp.json()["divisions"]
            if group["fighters"]
        )

        resp2 = client.get(f"/fighters/{fighter_id}")
        model_point = resp2.json()["model_history"][0]
        assert "fight_id" in model_point
        assert "fight_sequence" in model_point
        assert "model_score" in model_point
        assert "opponent_name" in model_point
        assert "result" in model_point
        assert "event" in model_point

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
