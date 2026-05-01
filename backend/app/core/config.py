"""Application configuration via pydantic-settings."""
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    APP_NAME: str = "DAWNSTAR Family Health Keeper"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/health.db"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60

    # AI Providers
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OLLAMA_LOCAL_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "medgemma"
    OLLAMA_TEXT_MODEL: str = "gemma3:4b"
    OLLAMA_TIMEOUT: int = 90  # seconds — per-call timeout for Ollama requests

    # Storage
    STORAGE_PATH: str = "./data/attachments"

    # AI Verification
    AI_VERIFICATION_ENABLED: bool = True

    def model_post_init(self, __context) -> None:
        """Validate settings after loading."""
        if self.APP_ENV == "production":
            self.DEBUG = False
            if not self.DATABASE_URL.startswith("postgresql"):
                raise ValueError(
                    "DATABASE_URL must use PostgreSQL in production! "
                    "Set DATABASE_URL=postgresql+asyncpg://user:pass@host/db in .env"
                )
            logger.info("Running in PRODUCTION mode")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
