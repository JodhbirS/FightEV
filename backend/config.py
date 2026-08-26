from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/fightev.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
