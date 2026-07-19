"""Application configuration via pydantic-settings."""

import logging
import os
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
    APP_VERSION: str = "1.2.1"
    DEBUG: bool = False
    # Root log level (DEBUG/INFO/WARNING/ERROR/CRITICAL). Default WARNING keeps
    # the journal quiet; raise it for diagnosis without a rebuild.
    LOG_LEVEL: str = "WARNING"

    # Security
    SECRET_KEY: str
    # Dedicated Fernet key for encrypting files/2FA secrets at rest. Decoupled
    # from SECRET_KEY (JWT signing) so rotating the JWT key doesn't render every
    # encrypted file unrecoverable. Empty → fall back to SECRET_KEY-derived key
    # (legacy behaviour). Generated on .deb install (see packaging/debian/postinst).
    ENCRYPTION_KEY: str = ""
    # JWT issuer/audience claims (token-confusion hardening).
    JWT_ISSUER: str = "health-manager"
    JWT_AUDIENCE: str = "health-manager-web"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/health.db"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    # Stricter limit for auth endpoints (login/register). Override to a large
    # value for local E2E runs so the suite isn't throttled (prod keeps 10/min).
    AUTH_RATE_LIMIT_REQUESTS: int = 10
    AUTH_RATE_LIMIT_WINDOW: int = 60

    # Max request body sizes (MB), enforced by the request-size middleware in
    # main.py. Tiered by path so large scanned-PDF batches aren't rejected at
    # the upload gate while general JSON stays capped low. Tune per deployment
    # via config.env without a rebuild. (backup restore gets the largest cap.)
    MAX_REQUEST_SIZE_MB: int = 50  # general API JSON payloads
    MAX_UPLOAD_SIZE_MB: int = 500  # file uploads: /records/extract*, /attachments
    MAX_BACKUP_SIZE_MB: int = 500  # backup restore

    # Redis
    REDIS_URL: str = ""  # Empty = in-memory fallback (dev mode)

    # Health check
    HEALTH_CHECK_SECRET: str = ""  # Required in prod; falls back to SECRET_KEY[:16] in dev

    # Scheduler
    RUN_SCHEDULER: bool = True  # Set false when scheduler runs in separate container

    # AI Providers
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OLLAMA_LOCAL_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3"
    OLLAMA_TEXT_MODEL: str = "qwen3"
    OLLAMA_TIMEOUT: int = 90  # seconds — per-call timeout for Ollama requests
    # Keep the model resident in memory between calls so the local fallback
    # doesn't re-pay the cold-load (~9s on CPU) on every extraction.
    OLLAMA_KEEP_ALIVE: str = "30m"
    # Per-cloud-provider failover cap (seconds) for document extraction: a
    # slow/dead cloud key is abandoned after this and the next provider is tried.
    EXTRACTION_PROVIDER_TIMEOUT: int = 15
    # CPU-inference thread pinning. Ollama is CPU-only on this hardware (no
    # CUDA) and commonly defaults ``num_thread`` to *physical* cores, ignoring
    # SMT. Setting it to the logical core count (``os.cpu_count()``) uses the
    # full 6C/12T and measurably cuts prompt-eval wall-clock on the local
    # fallback path. Set 0 to omit and let Ollama auto-select.
    OLLAMA_NUM_THREAD: int = os.cpu_count() or 8

    # External drug-information APIs (all server-side only — never sent to the
    # client). DrugBank's Clinical API is a paid subscription; leaving
    # DRUGBANK_API_KEY empty keeps drug-drug interaction checking on the existing
    # AI (Ollama/cloud) path. openFDA and RxNorm are free and need no key.
    DRUGBANK_API_KEY: str = ""
    DRUGBANK_REGION: str = "us"  # at/ca/eu/... — filters DrugBank results
    OPENFDA_API_KEY: str = ""  # Optional; raises openFDA rate limits (1k/day→120k/day)
    OPENFDA_BASE_URL: str = "https://api.fda.gov"
    RXNORM_BASE_URL: str = "https://rxnav.nlm.nih.gov/REST"

    # External health-information APIs (free, no key) for patient education,
    # clinical-trial search, and full drug labels. All degrade to empty on failure.
    MEDLINEPLUS_CONNECT_URL: str = "https://connect.medlineplus.gov/service"
    CLINICALTRIALS_BASE_URL: str = "https://clinicaltrials.gov/api/v2"
    # NIH Clinical Tables — free-text condition → ICD-10-CM code + synonyms.
    # Powers the disease & conditions lookup (unlocks the MedlinePlus Connect
    # coded endpoint from free-text diagnoses). Keyless.
    CLINICALTABLES_BASE_URL: str = "https://clinicaltables.nlm.nih.gov"
    DAILYMED_BASE_URL: str = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
    # Health Canada Drug Product Database — DIN/code lookup only (no name search).
    HEALTH_CANADA_DPD_URL: str = "https://health-products.canada.ca/api/drug"
    # GOV.UK search API — powers MHRA drug alerts (UK equivalent of openFDA recalls).
    GOV_UK_SEARCH_URL: str = "https://www.gov.uk/api/search.json"

    # Cloud provider models (configurable so they can be swapped without code
    # edits). OpenRouter defaults to FREE-tier models (the ":free" suffix) to
    # avoid 402 "payment required" on paid models — they're rate-limited, but
    # the provider race tolerates a throttled contender. Override any in .env.
    OPENROUTER_TEXT_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    OPENROUTER_VISION_MODEL: str = "google/gemma-4-31b-it:free"
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"

    # Storage
    STORAGE_PATH: str = "./data/attachments"
    STORAGE_BACKEND: str = "local"
    # PDF optimization on ingest (ghostscript image downsampling). Lossy —
    # embedded images are downsampled per PDF_OPTIMIZE_DPI. No-op if gs missing.
    OPTIMIZE_PDFS: bool = True
    PDF_OPTIMIZE_DPI: str = "ebook"  # screen(72) | ebook(150) | printer(300) | prepress

    # AI Verification
    AI_VERIFICATION_ENABLED: bool = True

    # Email notifications were removed (email_service.py is parked in
    # trash2review). Re-add an EMAIL_* block here if email is revived.

    def model_post_init(self, __context) -> None:
        """Validate settings after loading."""
        if self.APP_ENV == "production":
            self.DEBUG = False
            # SQLite is a supported production backend for single-server
            # self-hosted deployments (WAL mode + foreign keys enabled). We no
            # longer hard-require PostgreSQL — only warn that, without Redis,
            # rate limiting and the insight cache fall back to per-process
            # in-memory state (fine for one worker, imprecise across many).
            if not self.HEALTH_CHECK_SECRET:
                raise ValueError(
                    "HEALTH_CHECK_SECRET must be set in production! "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(24))"'
                )
            if not self.REDIS_URL:
                logger.warning(
                    "REDIS_URL not set — rate limiting and cache will use "
                    "in-memory fallback (per-process; use 1 worker or add Redis)"
                )
            logger.info(
                "Running in PRODUCTION mode (db=%s)",
                "postgresql" if self.DATABASE_URL.startswith("postgresql") else "sqlite",
            )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
