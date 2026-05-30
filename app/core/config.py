# .env.example
# ---------------------------------------------------------------------------
# JWT_SECRET=change-me-to-a-long-random-string
# JWT_ALGORITHM=HS256
# JWT_EXPIRE_MINUTES=480
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/auditforge
# STORAGE_PATH=storage
# IDEALS_DIR=ideals
# FUZZY_THRESHOLD_DEFAULT=80
# ---------------------------------------------------------------------------

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    storage_path: str = "storage"
    ideals_dir: str = "ideals"
    fuzzy_threshold_default: int = 80

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
