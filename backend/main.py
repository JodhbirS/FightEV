import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from database import engine, get_db, Base, SessionLocal
from models import Fighter, Fight, EloSnapshot
from schemas import (
    FighterListItem,
    FighterListResponse,
    FighterDetail,
    FightHistoryItem,
    EloPoint,
    FightOut,
)
from elo_engine import UFCEloEngine, compute_metrics

# --- Startup: create tables + load Elo engine for card predictions ---

Base.metadata.create_all(bind=engine)

_elo_engine = UFCEloEngine()


def _load_elo_engine():
    """Load all fights from DB into the in-memory Elo engine for card predictions."""
    db = SessionLocal()
    try:
        fights = (
            db.query(Fight)
            .order_by(Fight.id.asc())
            .all()
        )

        class _Row:
            """Mimics a DataFrame row for the existing Elo engine."""
            def __init__(self, f1_name, f2_name, result, method, round_num):
                self.fighter_1 = f1_name
                self.fighter_2 = f2_name
                self.result = result
                self.method = method
                self.round = round_num

        # Build fighter ID->name lookup
        fighters = {f.id: f.name for f in db.query(Fighter).all()}

        for fight in fights:
            row = _Row(
                fighters[fight.fighter_1_id],
                fighters[fight.fighter_2_id],
                fight.result,
                fight.method,
                fight.round,
            )
            _elo_engine.process_single_fight(row)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_elo_engine()
    yield


app = FastAPI(
    title="FightEV API",
    description="UFC fight predictions powered by Elo ratings and expected value analysis.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://frontend:5173",
        "https://fightev.vercel.app",
        "https://vercel.app",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _load_current_card():
    card_path = "data/card.json" if os.path.exists("data/card.json") else "backend/data/card.json"
    if not os.path.exists(card_path):
        return []
    try:
        with open(card_path) as f:
            raw = json.load(f)
        return [
            (bout["fighter1"], bout["fighter2"], bout["odds1"], bout["odds2"])
            for bout in raw
        ]
    except Exception:
        return []


@app.get("/fights", response_model=List[FightOut], summary="Upcoming fight card predictions")
def get_fights():
    """Return the current UFC fight card with Elo-based predictions and expected value analysis."""
    fights = _load_current_card()
    return compute_metrics(_elo_engine, fights)


INACTIVITY_FIGHT_THRESHOLD = 750  # ~1.5 years of UFC events (~500 fights/yr)



@app.get("/fighters", response_model=FighterListResponse, summary="Paginated list of fighters")
def get_fighters(
    limit: int = Query(default=20, ge=1, le=100, description="Number of fighters per page"),
    offset: int = Query(default=0, ge=0, description="Number of fighters to skip"),
    search: str = Query(default="", description="Filter fighters by name (case-insensitive)"),
    division: str = Query(default="", description="Filter fighters by weight class / division"),
    db: Session = Depends(get_db),
):
    """
    Return a paginated list of UFC fighters with their current Elo rating.
    Supports optional name search and weight class division filtering.
    Fighters who have not fought in > 1.5 years have their current_elo set to 0.0
    and is_active set to False. Active fighters are ordered by highest Elo first.
    """
    max_fight_id = db.query(func.max(Fight.id)).scalar() or 0

    latest_snap = (
        db.query(
            EloSnapshot.fighter_id,
            func.max(EloSnapshot.fight_id).label("max_fight_id"),
        )
        .group_by(EloSnapshot.fighter_id)
        .subquery()
    )

    query = (
        db.query(
            Fighter.id,
            Fighter.name,
            Fighter.weight_class,
            EloSnapshot.elo_after.label("raw_elo"),
            latest_snap.c.max_fight_id.label("last_fight_id"),
        )
        .join(latest_snap, Fighter.id == latest_snap.c.fighter_id)
        .join(
            EloSnapshot,
            (EloSnapshot.fighter_id == latest_snap.c.fighter_id)
            & (EloSnapshot.fight_id == latest_snap.c.max_fight_id),
        )
    )

    if search:
        query = query.filter(Fighter.name.ilike(f"%{search}%"))

    if division:
        query = query.filter(Fighter.weight_class.ilike(f"%{division}%"))

    total = query.count()

    is_active_case = case(
        (latest_snap.c.max_fight_id >= max_fight_id - INACTIVITY_FIGHT_THRESHOLD, 1),
        else_=0,
    )

    rows = (
        query.order_by(is_active_case.desc(), EloSnapshot.elo_after.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    fighters = []
    for row in rows:
        is_active = bool(row.last_fight_id >= max_fight_id - INACTIVITY_FIGHT_THRESHOLD)
        fighters.append(
            FighterListItem(
                id=row.id,
                name=row.name,
                weight_class=row.weight_class,
                current_elo=round(row.raw_elo, 1) if is_active else 0.0,
                is_active=is_active,
            )
        )

    return FighterListResponse(
        total=total,
        limit=limit,
        offset=offset,
        fighters=fighters,
    )


def _build_fighter_detail(fighter: Fighter, db: Session) -> FighterDetail:
    max_fight_id = db.query(func.max(Fight.id)).scalar() or 0

    # Get all Elo snapshots for this fighter, ordered by fight ID (chronological)
    snapshots = (
        db.query(EloSnapshot)
        .filter(EloSnapshot.fighter_id == fighter.id)
        .order_by(EloSnapshot.fight_id.asc())
        .all()
    )

    last_snap = snapshots[-1] if snapshots else None
    is_active = bool(last_snap and (last_snap.fight_id >= max_fight_id - INACTIVITY_FIGHT_THRESHOLD))
    current_elo = round(last_snap.elo_after, 2) if (last_snap and is_active) else 0.0

    # Build fight history + elo history
    fight_history = []
    elo_history = []
    wins = losses = draws = 0

    for seq, snap in enumerate(snapshots, 1):
        fight = db.query(Fight).filter(Fight.id == snap.fight_id).first()
        opponent = db.query(Fighter).filter(Fighter.id == snap.opponent_id).first()

        if snap.result == "win":
            wins += 1
        elif snap.result == "loss":
            losses += 1
        elif snap.result == "draw":
            draws += 1

        fight_history.append(FightHistoryItem(
            id=fight.id if fight else snap.fight_id,
            event=fight.event if fight else "UFC",
            opponent_name=opponent.name if opponent else "Unknown",
            result=snap.result,
            method=fight.method if fight else "Unknown",
            round=fight.round if fight else 0,
            time=fight.time if fight else "",
        ))

        elo_history.append(EloPoint(
            fight_id=fight.id if fight else snap.fight_id,
            fight_sequence=seq,
            elo_after=snap.elo_after,
            opponent_name=opponent.name if opponent else "Unknown",
            result=snap.result,
            event=fight.event if fight else "UFC",
        ))

    return FighterDetail(
        id=fighter.id,
        name=fighter.name,
        weight_class=fighter.weight_class,
        current_elo=current_elo,
        is_active=is_active,
        total_fights=len(snapshots),
        wins=wins,
        losses=losses,
        draws=draws,
        fight_history=fight_history,
        elo_history=elo_history,
    )


@app.get("/fighters/{fighter_id}", response_model=FighterDetail, summary="Fighter detail with Elo history")
def get_fighter(fighter_id: int, db: Session = Depends(get_db)):
    """
    Return detailed information about a specific fighter, including their
    complete fight history and Elo rating over time for charting.
    """
    fighter = db.query(Fighter).filter(Fighter.id == fighter_id).first()
    if not fighter:
        raise HTTPException(status_code=404, detail="Fighter not found")
    return _build_fighter_detail(fighter, db)


@app.get("/fighters/by-name/{fighter_name}", response_model=FighterDetail, summary="Fighter detail by name")
def get_fighter_by_name(fighter_name: str, db: Session = Depends(get_db)):
    """
    Return detailed information about a fighter by name (case-insensitive fuzzy match).
    """
    fighter = db.query(Fighter).filter(Fighter.name.ilike(fighter_name)).first()
    if not fighter:
        # Fallback to partial match
        fighter = db.query(Fighter).filter(Fighter.name.ilike(f"%{fighter_name}%")).first()
    if not fighter:
        raise HTTPException(status_code=404, detail="Fighter not found")
    return _build_fighter_detail(fighter, db)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
