# settings.py
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Core service
    PORT: int = 8000
    WORKERS: int = 2
    ENV: str = "dev"                # dev | staging | prod
    LOG_LEVEL: str = "info"         # debug | info | warning | error

    # HTTP client config
    HTTP_TIMEOUT_SECONDS: int = 10
    HTTP_MAX_RETRIES: int = 1
    HTTP_MAX_HOST_CONCURRENCY: int = 2

    # Cache
    CACHE_TTL_DAYS: int = 7
    REDIS_URL: Optional[str] = None

    # Config files
    VENUE_WHITELISTS_PATH: str = "config/venues.json"
    ALIASES_PATH: str = "config/aliases.json"

    # External APIs (optional)
    PPLX_API_KEY: Optional[str] = None
    SENTRY_DSN: Optional[str] = None

    class Config:
        env_file = ".env"  # automatically load from .env file
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

