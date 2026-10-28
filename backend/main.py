import json
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from ensemble_engine import EnsemblePredictor, compute_metrics
from models import Fight, Fighter
from schemas import (
    FightHistoryItem,
    FightOut,
    FighterDetail,
    FighterListItem,
    FighterListResponse,
    ModelPoint,
)

Base.metadata.create_all(bind=engine)
_predictor = EnsemblePredictor()


def _load_predictor() -> None:
    db = SessionLocal()
    try:
        fighters = {fighter.id: fighter.name for fighter in db.query(Fighter).all()}
        fights = db.query(Fight).order_by(Fight.event_date.asc().nullsfirst(), Fight.id.asc()).all()
        _predictor.fit([
            {
                "fighter_1": fighters[fight.fighter_1_id],
                "fighter_2": fighters[fight.fighter_2_id],
                "result": fight.result,
                "method": fight.method,
                "event_date": fight.event_date,
            }
            for fight in fights
        ])
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_predictor()
    yield


app = FastAPI(
    title="FightEV API",
    description="UFC fight predictions powered by a CPU-only ensemble model.",
    version="3.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://frontend:5173",
        "https://fightev.vercel.app", "https://vercel.app",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

INACTIVITY_DAYS = 913
FEATURED_FIGHTERS = (
    "Islam Makhachev",
    "Alexander Volkanovski",
    "Joshua Van",
    "Alexandre Pantoja",
    "Petr Yan",
    "Ilia Topuria",
    "Alex Pereira",
    "Tom Aspinall",
    "Dricus Du Plessis",
    "Khamzat Chimaev",
)
def _load_current_card() -> list[tuple[str, str, int, int]]:
    path = "data/card.json" if os.path.exists("data/card.json") else "backend/data/card.json"
    if not os.path.exists(path):
        return []
    with open(path) as card_file:
        return [
            (bout["fighter1"], bout["fighter2"], bout["odds1"], bout["odds2"])
            for bout in json.load(card_file)
        ]


@app.get("/fights", response_model=List[FightOut])
def get_fights():
    return compute_metrics(_predictor, _load_current_card())


@app.get("/fighters", response_model=FighterListResponse)
def get_fighters(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=""),
    division: str = Query(default=""),
    db: Session = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=INACTIVITY_DAYS)
    active_ids = {
        fighter_id
        for fighter_id, latest_date in db.query(
            Fighter.id,
            func.max(Fight.event_date),
        ).join(
            Fight,
            or_(Fight.fighter_1_id == Fighter.id, Fight.fighter_2_id == Fighter.id),
        ).filter(
            Fight.event_date.is_not(None),
        ).group_by(Fighter.id).all()
        if latest_date >= cutoff
    }
    query = db.query(Fighter).filter(Fighter.id.in_(active_ids))
    if search:
        query = query.filter(Fighter.name.ilike(f"%{search}%"))
    if division:
        query = query.filter(Fighter.weight_class.ilike(f"%{division}%"))
    fighters = query.all()
    if not search:
        featured = {name: index for index, name in enumerate(FEATURED_FIGHTERS)}
        fighters = [fighter for fighter in fighters if fighter.name in featured]
        fighters.sort(key=lambda fighter: featured[fighter.name])
    else:
        fighters.sort(key=lambda fighter: fighter.name.lower())

    selected = fighters[offset:offset + limit]
    return FighterListResponse(
        total=len(fighters),
        limit=limit,
        offset=offset,
        fighters=[
            FighterListItem(
                id=fighter.id,
                name=fighter.name,
                weight_class=fighter.weight_class,
                is_active=True,
            )
            for fighter in selected
        ],
    )


def _build_fighter_detail(fighter: Fighter, db: Session) -> FighterDetail:
    fights = (
        db.query(Fight)
        .filter((Fight.fighter_1_id == fighter.id) | (Fight.fighter_2_id == fighter.id))
        .order_by(Fight.event_date.asc().nullsfirst(), Fight.id.asc())
        .all()
    )
    opponent_ids = {
        fight.fighter_2_id if fight.fighter_1_id == fighter.id else fight.fighter_1_id
        for fight in fights
    }
    fighters = {
        item.id: item.name
        for item in db.query(Fighter).filter(Fighter.id.in_(opponent_ids)).all()
    }
    cutoff = date.today() - timedelta(days=INACTIVITY_DAYS)
    last_fight = fights[-1] if fights else None
    is_active = bool(last_fight and last_fight.event_date and last_fight.event_date >= cutoff)
    wins = losses = draws = 0
    history = []
    method_history = []
    for sequence, fight in enumerate(fights, 1):
        is_first = fight.fighter_1_id == fighter.id
        opponent_id = fight.fighter_2_id if is_first else fight.fighter_1_id
        result = fight.result if is_first else (
            "loss" if fight.result == "win" else fight.result
        )
        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        elif result == "draw":
            draws += 1
        history.append(FightHistoryItem(
            id=fight.id, event=fight.event, opponent_name=fighters.get(opponent_id, "Unknown"),
            result=result, method=fight.method, round=fight.round, time=fight.time,
        ))
        method_history.append(ModelPoint(
            fight_id=fight.id, fight_sequence=sequence, opponent_name=fighters.get(opponent_id, "Unknown"),
            result=result, method=fight.method, event=fight.event,
        ))
    return FighterDetail(
        id=fighter.id, name=fighter.name, weight_class=fighter.weight_class,
        is_active=is_active, total_fights=len(fights), wins=wins, losses=losses,
        draws=draws, fight_history=history, method_history=method_history,
    )


@app.get("/fighters/{fighter_id}", response_model=FighterDetail)
def get_fighter(fighter_id: int, db: Session = Depends(get_db)):
    fighter = db.query(Fighter).filter(Fighter.id == fighter_id).first()
    if not fighter:
        raise HTTPException(status_code=404, detail="Fighter not found")
    return _build_fighter_detail(fighter, db)


@app.get("/fighters/by-name/{fighter_name}", response_model=FighterDetail)
def get_fighter_by_name(fighter_name: str, db: Session = Depends(get_db)):
    fighter = db.query(Fighter).filter(Fighter.name.ilike(fighter_name)).first()
    if not fighter:
        fighter = db.query(Fighter).filter(Fighter.name.ilike(f"%{fighter_name}%")).first()
    if not fighter:
        raise HTTPException(status_code=404, detail="Fighter not found")
    return _build_fighter_detail(fighter, db)
