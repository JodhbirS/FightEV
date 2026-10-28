from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date
from sqlalchemy.orm import relationship

from database import Base


class Fighter(Base):
    __tablename__ = "fighters"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    weight_class = Column(String, nullable=True)



class Fight(Base):
    __tablename__ = "fights"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event = Column(String, nullable=False)
    event_date = Column(Date, nullable=True, index=True)
    fighter_1_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    fighter_2_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    result = Column(String, nullable=False)  # "win", "draw", "nc"
    method = Column(String, nullable=False)
    round = Column(Integer, nullable=False)
    time = Column(String, nullable=False)

    fighter_1 = relationship("Fighter", foreign_keys=[fighter_1_id])
    fighter_2 = relationship("Fighter", foreign_keys=[fighter_2_id])

    # No unique constraint — rematches at the same event are possible
    # (e.g. tournament-style events like UFC - Ultimate Japan)
