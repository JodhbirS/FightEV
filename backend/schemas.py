from pydantic import BaseModel
from typing import Optional


# --- /fighters list ---

class FighterListItem(BaseModel):
    id: int
    name: str
    weight_class: Optional[str] = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class FighterListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    fighters: list[FighterListItem]


# --- /fighters/{id} detail ---

class ModelPoint(BaseModel):
    fight_id: int
    fight_sequence: int
    opponent_name: str
    result: str
    finish: bool
    finish_rate: float
    event: str

    model_config = {"from_attributes": True}


class FightHistoryItem(BaseModel):
    id: int
    event: str
    opponent_name: str
    result: str
    method: str
    round: int
    time: str

    model_config = {"from_attributes": True}


class FighterDetail(BaseModel):
    id: int
    name: str
    weight_class: Optional[str] = None
    is_active: bool = True
    total_fights: int
    wins: int
    losses: int
    draws: int
    fight_history: list[FightHistoryItem]
    model_history: list[ModelPoint]

    model_config = {"from_attributes": True}


# --- /fights card predictions ---

class FightOut(BaseModel):
    fighter1: str
    fighter2: str
    odds1: int
    odds2: int
    modelProb1: float
    modelProb2: float
    impProb1: float
    impProb2: float
    ev1: float
    ev2: float
    predWinner: int
    predMethod: str
    predMethodProb: float
    kelly1: float = 0.0
    kelly2: float = 0.0
