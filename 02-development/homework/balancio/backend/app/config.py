from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Balancio"
    app_currency: str = "MXN"
    jwt_secret: str = "change-me"
    jwt_expiration_hours: int = 8
    database_url: str = "sqlite:///./data/balancio.db"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
