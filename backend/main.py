import json
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from math import exp
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from ensemble_engine import EnsemblePredictor, compute_metrics
from models import Fight, Fighter
from schemas import (
    DivisionGroup,
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
        fights = db.query(Fight).order_by(Fight.event_date.asc().nullslast(), Fight.id.asc()).all()
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
UFC_DIVISIONS = (
    "Flyweight",
    "Bantamweight",
    "Featherweight",
    "Lightweight",
    "Welterweight",
    "Middleweight",
    "Light Heavyweight",
    "Heavyweight",
    "Women's Strawweight",
    "Women's Flyweight",
    "Women's Bantamweight",
)


def _canonical_division(weight_class: str | None) -> str | None:
    if not weight_class:
        return None
    normalized = " ".join(weight_class.replace("’", "'").split()).lower()
    for division in UFC_DIVISIONS:
        if normalized == division.lower():
            return division
    return None


def _division_power_scores(
    db: Session,
    fighters: list[Fighter],
) -> dict[int, float]:
    """Estimate division strength with a recency-weighted Bradley-Terry fit."""
    fighter_ids = {fighter.id for fighter in fighters}
    scores = {fighter.id: 0.0 for fighter in fighters}
    fights = db.query(Fight).filter(
        (Fight.fighter_1_id.in_(fighter_ids))
        | (Fight.fighter_2_id.in_(fighter_ids)),
        Fight.result.in_(("win", "draw")),
    ).all()
    all_ids = {
        fighter_id
        for fight in fights
        for fighter_id in (fight.fighter_1_id, fight.fighter_2_id)
    }
    scores.update({fighter_id: 0.0 for fighter_id in all_ids})
    today = date.today()

    for _ in range(40):
        gradients = {fighter_id: 0.0 for fighter_id in all_ids}
        for fight in fights:
            if fight.result == "draw":
                outcome = 0.5
            else:
                outcome = 1.0
            first_score = scores[fight.fighter_1_id]
            second_score = scores[fight.fighter_2_id]
            probability = 1.0 / (1.0 + exp(second_score - first_score))
            age_days = max(0, (today - (fight.event_date or today)).days)
            weight = exp(-age_days / 1095.0)
            error = weight * (outcome - probability)
            gradients[fight.fighter_1_id] += error
            gradients[fight.fighter_2_id] -= error
        for fighter_id in fighter_ids:
            scores[fighter_id] += 0.18 * gradients[fighter_id] - 0.01 * scores[fighter_id]

    average = sum(scores.values()) / max(1, len(scores))
    for fighter in fighters:
        fights_count = sum(
            1 for fight in fights
            if fighter.id in (fight.fighter_1_id, fight.fighter_2_id)
        )
        confidence = fights_count / (fights_count + 8.0)
        scores[fighter.id] = average + confidence * (scores[fighter.id] - average)
    return scores


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


def _latest_dates(db: Session) -> dict[int, date]:
    latest: dict[int, date] = {}
    for fight in db.query(Fight).all():
        if not fight.event_date:
            continue
        for fighter_id in (fight.fighter_1_id, fight.fighter_2_id):
            if fighter_id not in latest or fight.event_date > latest[fighter_id]:
                latest[fighter_id] = fight.event_date
    return latest


@app.get("/fighters", response_model=FighterListResponse)
def get_fighters(
    db: Session = Depends(get_db),
):
    cutoff = date.today() - timedelta(days=INACTIVITY_DAYS)
    latest = _latest_dates(db)
    by_division: dict[str, list[Fighter]] = {division: [] for division in UFC_DIVISIONS}
    for fighter in db.query(Fighter).all():
        division = _canonical_division(fighter.weight_class)
        if division and latest.get(fighter.id) and latest[fighter.id] >= cutoff:
            by_division[division].append(fighter)

    groups = []
    for division in UFC_DIVISIONS:
        division_scores = _division_power_scores(db, by_division[division])
        fighters = sorted(
            by_division[division],
            key=lambda fighter: (
                division_scores[fighter.id],
                latest[fighter.id],
                fighter.name,
            ),
            reverse=True,
        )[:5]
        groups.append(DivisionGroup(
            name=division,
            fighters=[
                FighterListItem(
                    id=fighter.id,
                    name=fighter.name,
                    weight_class=division,
                    model_score=round(
                        50.0 + 10.0 * division_scores[fighter.id], 1
                    ),
                    is_active=True,
                )
                for fighter in fighters
            ],
        ))
    return FighterListResponse(
        total=sum(len(group.fighters) for group in groups),
        divisions=groups,
    )


def _build_fighter_detail(fighter: Fighter, db: Session) -> FighterDetail:
    fights = (
        db.query(Fight)
        .filter((Fight.fighter_1_id == fighter.id) | (Fight.fighter_2_id == fighter.id))
        .order_by(Fight.event_date.asc().nullslast(), Fight.id.asc())
        .all()
    )
    fighters = {item.id: item.name for item in db.query(Fighter).all()}
    profile = _predictor.profiles[fighter.name]
    cutoff = date.today() - timedelta(days=INACTIVITY_DAYS)
    last_fight = fights[-1] if fights else None
    is_active = bool(last_fight and last_fight.event_date and last_fight.event_date >= cutoff)
    wins = losses = draws = 0
    history = []
    model_history = []
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
        score = round(100 * wins / max(1, wins + losses), 1)
        history.append(FightHistoryItem(
            id=fight.id, event=fight.event, opponent_name=fighters.get(opponent_id, "Unknown"),
            result=result, method=fight.method, round=fight.round, time=fight.time,
        ))
        model_history.append(ModelPoint(
            fight_id=fight.id, fight_sequence=sequence, model_score=score,
            opponent_name=fighters.get(opponent_id, "Unknown"), result=result, event=fight.event,
        ))
    return FighterDetail(
        id=fighter.id, name=fighter.name, weight_class=fighter.weight_class,
        model_score=round(100 * profile.wins / max(1, profile.experience), 1) if is_active else 0.0,
        is_active=is_active, total_fights=len(fights), wins=wins, losses=losses,
        draws=draws, fight_history=history, model_history=model_history,
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
