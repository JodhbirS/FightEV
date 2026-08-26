from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class Fighter(Base):
    __tablename__ = "fighters"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    weight_class = Column(String, nullable=True)

    elo_snapshots = relationship("EloSnapshot", back_populates="fighter", foreign_keys="EloSnapshot.fighter_id")


class Fight(Base):
    __tablename__ = "fights"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event = Column(String, nullable=False)
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


class EloSnapshot(Base):
    __tablename__ = "elo_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fighter_id = Column(Integer, ForeignKey("fighters.id"), nullable=False, index=True)
    fight_id = Column(Integer, ForeignKey("fights.id"), nullable=False)
    elo_before = Column(Float, nullable=False)
    elo_after = Column(Float, nullable=False)
    opponent_id = Column(Integer, ForeignKey("fighters.id"), nullable=False)
    result = Column(String, nullable=False)  # "win"/"loss"/"draw"/"nc" from this fighter's POV

    fighter = relationship("Fighter", back_populates="elo_snapshots", foreign_keys=[fighter_id])
    opponent = relationship("Fighter", foreign_keys=[opponent_id])
    fight = relationship("Fight")
