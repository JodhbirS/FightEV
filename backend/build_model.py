import os

import joblib

from database import SessionLocal
from ensemble_engine import EloLogisticPredictor
from models import Fight, Fighter


MODEL_PATH = os.path.join(os.path.dirname(__file__), "data", "model.joblib")


def build_model() -> None:
    db = SessionLocal()
    try:
        fighters = {fighter.id: fighter.name for fighter in db.query(Fighter).all()}
        fights = db.query(Fight).order_by(
            Fight.event_date.asc().nullslast(),
            Fight.id.asc(),
        ).all()
        predictor = EloLogisticPredictor()
        predictor.fit([
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

    joblib.dump(predictor, MODEL_PATH)
    print(f"Saved trained predictor to {MODEL_PATH}")


if __name__ == "__main__":
    build_model()
