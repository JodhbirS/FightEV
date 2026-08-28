import os
from pathlib import Path
from pydantic_settings import BaseSettings

_BASE_DIR = Path(__file__).resolve().parent
_DB_PATH = _BASE_DIR / "data" / "fightev.db"


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH}")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

