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
    APP_VERSION: str = "1.2.10"
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
    # Default to the ``qwen3:4b`` tag (the actually-installed model). The bare
    # ``qwen3`` alias resolves to ``qwen3:latest`` which is usually NOT pulled on
    # this box → a 404 that silently broke the local fallback. Pin the tag.
    OLLAMA_MODEL: str = "qwen3:4b"
    OLLAMA_TEXT_MODEL: str = "qwen3:4b"
    # Optional faster/smaller model for clean-text extraction (text path only —
    # embedded-text PDFs and good-OCR images). When set, the Ollama text-
    # extraction entry uses this instead of OLLAMA_TEXT_MODEL, cutting CPU
    # prompt-eval + generation time on the common easy case; vision/hard cases
    # still use OLLAMA_VISION_MODEL / OLLAMA_TEXT_MODEL. Empty (default) = no
    # change. EVAL-GATED: validate accuracy with ``tests/extraction/`` (golden
    # F1) against your chosen fast model before enabling in prod, and bump
    # EXTRACTION_CACHE_VERSION isn't needed — the fingerprint already includes
    # this model so the cache self-invalidates.
    OLLAMA_FAST_MODEL: str = ""
    # Vision-capable model for local image/PDF OCR-via-LLM. Empty = local vision
    # DISABLED (cloud handles vision; qwen3 is text-only). To enable offline
    # document vision, ``ollama pull llama3.2-vision`` (or ``minicpm-v``) and set
    # this. The provider gracefully skips (returns None) when unset or not pulled.
    OLLAMA_VISION_MODEL: str = ""
    OLLAMA_TIMEOUT: int = 90  # seconds — per-call timeout for Ollama requests
    # How long Ollama keeps the model resident AFTER a call. Default keeps the
    # model warm for 30 min so back-to-back family extractions skip the ~9 s+
    # CPU cold-load each time (the previous 2 m default unloaded it between
    # typical uses). Costs ~3 GB of resident RAM while alive — acceptable on a
    # dedicated family box; set "2m" again on memory-constrained hosts. The
    # startup warmup (OLLAMA_WARMUP_ON_STARTUP) loads it once at boot so the
    # FIRST extraction isn't cold either.
    OLLAMA_KEEP_ALIVE: str = "30m"
    # Fire one throwaway generation per configured Ollama model at startup so the
    # model is resident in memory before the first user extraction. Runs as a
    # non-blocking background task (it doesn't delay app readiness). Disable if
    # you don't want the ~9-20 s of CPU at boot.
    OLLAMA_WARMUP_ON_STARTUP: bool = True
    # Per-cloud-provider failover cap (seconds) for document extraction: a
    # slow/dead cloud key is abandoned after this and the next provider is tried.
    EXTRACTION_PROVIDER_TIMEOUT: int = 15
    # Hard wall-clock cap (seconds) for the LOCAL Ollama extraction path. The
    # local path is the last-resort fallback and was previously unbounded — so a
    # stuck qwen3 thinking-model generation could pin the CPU for tens of
    # minutes (observed: 47 min at ~10 cores, freezing the whole box). 300 s is
    # generous enough for a genuine CPU extraction (prompt eval + ~2k output
    # tokens on a 4 B model) yet bounds the runaway. If it ever fires, the
    # extraction fails gracefully instead of hanging the UI at 45 % forever.
    EXTRACTION_LOCAL_TIMEOUT: int = 300
    # Race the cloud providers in parallel (first non-empty result wins) instead
    # of strict sequential failover. OFF by default: sequential first-success
    # wastes no API calls and is tolerant of rate limits, and the dead-key tax
    # is already removed by the pre-flight health probe (provider_health). Turn
    # ON only when you have several healthy cloud keys and want minimum-latency
    # extraction at the cost of a few wasted calls on providers that lose the
    # race. The local Ollama entry is never raced (that would pin the CPU on a
    # cancelled generation); it stays the sequential last resort.
    EXTRACTION_RACE_PROVIDERS: bool = False
    # Pages of OCR text packed into one extraction call on the scanned-PDF text
    # path. Larger = fewer LLM calls (N/pages_per_chunk) at the cost of a bigger
    # prompt per call (each is still capped at 10k chars). 5 is a good default
    # for typical 1-6 page medical docs — a 5-page scan becomes ONE call instead
    # of two. The local CPU path benefits most (Ollama serializes, so each call
    # saved is ~60-120s).
    EXTRACTION_PAGES_PER_CHUNK: int = 5
    # How many page images to send in ONE multi-image vision call on the
    # scanned-PDF vision fallback. Cloud vision models (Gemini/GPT/Groq) accept
    # multiple images per request; packing k pages into one call turns N
    # per-page calls into N/k calls — the biggest local-mode win for multi-page
    # scans that failed OCR (a 9-page scan drops from 9 calls to 3). 1 disables
    # multi-image (legacy one-call-per-page behaviour).
    EXTRACTION_VISION_BATCH_SIZE: int = 3
    # Max concurrent vision batch calls on the scanned-PDF vision fallback
    # (cloud path). Each batch is one multi-image API call; running them in
    # parallel cuts multi-page wall-clock, but unbounded fan-out risks rate
    # limits on providers like Groq/OpenRouter. 4 is a safe default that lets a
    # 12-page scan (4 batches of 3) finish in one round-trip without tripping
    # typical rate ceilings. Local Ollama is always sequential (it serializes
    # one generation per model regardless).
    EXTRACTION_VISION_BATCH_CONCURRENCY: int = 4
    # Longest-side cap (px) applied to raw image uploads before they become a
    # vision payload. Phone photos of documents are commonly ~4000px / multi-MB
    # and were sent raw; vision providers tile-bill by resolution and process
    # smaller images faster, so capping + JPEG re-encode cuts the payload ~10-20x
    # with no loss of medical legibility (the providers downscale internally
    # anyway — this saves bandwidth + image tokens, not visible detail). 1568 is
    # the OpenAI high-detail tile boundary. PDF pages are already DPI-bounded, so
    # this only affects the image/* OCR-via-LLM and image vision-only paths. 0
    # disables (sends the original bytes unchanged).
    EXTRACTION_VISION_MAX_DIM: int = 1568
    # Hard cap on generated tokens for cloud *extraction* calls (text + vision).
    # Soft cap on generated tokens for cloud *extraction* calls (text + vision).
    # Primary value is bounding pathological over-generation (cost); wall-clock
    # runaway is already bounded by EXTRACTION_PROVIDER_TIMEOUT. Tuned for
    # ACCURACY: 4096 = 2x the proven-local num_predict=2048 cap, giving headroom
    # so a dense extraction (long prescription list, sizable clinical_data) is
    # never truncated mid-JSON — a truncation would yield unparseable JSON and an
    # empty extraction (accuracy loss). If it ever bites, data_rate in
    # /ai/extraction-metrics drops and you can raise or disable (0) it. Applied
    # to Groq/OpenRouter/OpenAI (max_tokens) and Gemini (maxOutputTokens); the
    # local Ollama path is capped separately via num_predict, and OCR/transcription
    # are left uncapped (they can legitimately run long).
    EXTRACTION_MAX_TOKENS: int = 4096
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
    # Application Default Credentials for Gemini (alternative to the API key).
    # Path to a gcloud user-credentials JSON (``gcloud auth application-default
    # login``) or a service-account key. When set + readable, the Gemini
    # provider authenticates with an OAuth Bearer token derived from it and
    # routes through Vertex AI (which accepts the cloud-platform scope ADC
    # grants); the Generative Language API needs a scope gcloud won't grant, so
    # ADC only works via Vertex. The API key (Gen Lang API) remains the fallback
    # when no ADC is set. Leave empty to use the API-key path (default). Also
    # honors GOOGLE_APPLICATION_CREDENTIALS.
    GEMINI_ADC_FILE: str = ""
    # Vertex AI routing (used only when GEMINI_ADC_FILE is set). Set VERTEX_PROJECT
    # to the project that owns the ADC creds (e.g. gen-lang-client-0426752244).
    VERTEX_PROJECT: str = ""
    VERTEX_LOCATION: str = "us-central1"

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
