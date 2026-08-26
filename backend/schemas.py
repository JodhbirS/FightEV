from pydantic import BaseModel
from typing import Optional


# --- /fighters list ---

class FighterListItem(BaseModel):
    id: int
    name: str
    weight_class: Optional[str] = None
    current_elo: float

    model_config = {"from_attributes": True}


class FighterListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    fighters: list[FighterListItem]


# --- /fighters/{id} detail ---

class EloPoint(BaseModel):
    fight_id: int
    fight_sequence: int
    elo_after: float
    opponent_name: str
    result: str
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
    current_elo: float
    total_fights: int
    wins: int
    losses: int
    draws: int
    fight_history: list[FightHistoryItem]
    elo_history: list[EloPoint]

    model_config = {"from_attributes": True}
