"""Application configuration via pydantic-settings."""

import logging
import os
import tomllib
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _app_version() -> str:
    """Single source of truth: read the version from ``backend/pyproject.toml``.

    Keeps the app's reported version (``Settings.APP_VERSION``, surfaced in
    /health, /ai/status, the desktop about) in lockstep with the packaged
    version (the .deb build reads the same pyproject). Falls back to a literal
    only if the file can't be read (e.g. an exotic non-frozen runtime without
    the repo layout); the PyInstaller spec bundles pyproject.toml so the frozen
    sidecar reads the real value.
    """
    try:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception as exc:  # noqa: BLE001 — never block boot over a version read
        logger.debug("Could not read version from pyproject.toml: %s", exc)
        return "1.3.0"


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
    APP_VERSION: str = _app_version()
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
    # Per-job controls for low-resource / self-hosted deployments. Each heavy
    # background job can be disabled or retimed via env without touching code.
    # Defaults preserve existing behaviour — relax them on a constrained host
    # (e.g. an Ollama-only box that doesn't use reminders: REMINDERS_ENABLED=false,
    # or weekly integrity checks: FILE_INTEGRITY_CHECK_INTERVAL=604800).
    REMINDERS_ENABLED: bool = True
    REMINDER_POLL_INTERVAL: int = 60  # seconds between reminder sweeps
    AI_PROVIDER_HEALTH_CHECK_ENABLED: bool = True
    AI_HEALTH_CHECK_INTERVAL: int = 300  # already key-gated, so cheap when keyless
    # On startup, refresh each CLOUD provider's model list and auto-set the
    # latest economical-capable model (prevents stale/retired-model 404s, e.g.
    # Groq retiring llama-4-scout). Ollama is never auto-set (local free-text).
    # Always overwrites the active cloud model on each boot — set false to keep
    # manual Settings choices. See services/ai/model_autoselect.py.
    AI_AUTOTUNE_MODELS_ON_STARTUP: bool = True
    ANOMALY_DETECTION_ENABLED: bool = True
    ANOMALY_DETECTION_INTERVAL: int = 21600  # 6h
    FILE_INTEGRITY_CHECK_ENABLED: bool = True
    FILE_INTEGRITY_CHECK_INTERVAL: int = 86400  # daily; 604800 = weekly
    OCR_CONCURRENCY: int = 4  # parallel page OCR processes (PDF/image text path)

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
    # Suppress qwen3 reasoning (<think> blocks) on the insight/chat path
    # (ollama_chat + ollama_chat_stream). Thinking is slow on CPU — a long
    # reasoning trace can push Smart-Report/insight generation past proxy SSE
    # timeouts (e.g. Caddy's read_timeout) and the <think> tags leak into the
    # streamed JSON/prose and corrupt parsing. The extraction path already
    # suppresses this unconditionally for JSON; this extends the same speed-up
    # to conversational/insight generation. Turn off (false) only if you want
    # deeper (but much slower) reasoning and accept the longer wait.
    OLLAMA_SUPPRESS_THINK: bool = True

    # External drug-information APIs (all server-side only — never sent to the
    # client). DrugBank's Clinical API is a paid subscription; leaving
    # DRUGBANK_API_KEY empty keeps drug-drug interaction checking on the existing
    # AI (Ollama/cloud) path. openFDA and RxNorm are free and need no key.
    DRUGBANK_API_KEY: str = ""
    DRUGBANK_REGION: str = "us"  # at/ca/eu/... — filters DrugBank results
    OPENFDA_API_KEY: str = ""  # Optional; raises openFDA rate limits (1k/day→120k/day)
    # When RxNorm + the strength-stripping heuristic can't map a free-text med
    # name to a generic (common for non-US brands, e.g. "Ropark" → ropinirole),
    # ask the configured AI for the active ingredient, then validate it against
    # openFDA before use. Cached per brand. Disable to skip the AI round-trip.
    DRUG_GENERIC_AI_FALLBACK: bool = True
    OPENFDA_BASE_URL: str = "https://api.fda.gov"
    RXNORM_BASE_URL: str = "https://rxnav.nlm.nih.gov/REST"
    # Local drug catalog CSV (Indian brand→composition + metadata). Gitignored —
    # each deployment keeps its copy here; seed once via
    # `uv run python -m app.scripts.seed_drug_catalog`. Empty = no local catalog
    # (the drug-info service degrades to ABDM/RxNorm/openFDA/AI as before).
    DRUG_CATALOG_CSV: str = ""
    # Bulk Indian-medicine dataset (junioralive/Indian-Medicine-Dataset) raw CSV
    # — no auth. Seeded via seed_drug_catalog_github.
    INDIAN_MED_DATASET_URL: str = (
        "https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/"
        "main/DATA/indian_medicine_data.csv"
    )
    # parse.bot drugs.com API (rich monographs). Key-gated; empty = importer off.
    PARSE_BOT_API_KEY: str = ""
    PARSE_BOT_BASE_URL: str = "https://api.parse.bot/scraper/da04495a-c550-40b2-91b6-6a686616952d"
    # Kaggle drugs.com review dataset — token-gated. KAGGLE_API_TOKEN is read
    # from the env (never commit it). Dataset slug is configurable.
    KAGGLE_API_TOKEN: str = ""
    KAGGLE_DRUG_REVIEW_DATASET: str = "matiflatif/drugs-review-dataset"
    # ABDM Drug Registry (Ayushman Bharat Digital Mission — India's national drug
    # catalog). OAuth client_credentials: register on the ABDM sandbox to receive
    # a clientId/Secret, then set both here to enable Indian brand→generic
    # resolution, indication/contraindication, and substitute drugs. Server-side
    # only — never sent to the client. When unset, the ABDM provider returns
    # empty and the app degrades to RxNorm/openFDA/AI as before.
    ABDM_CLIENT_ID: str = ""
    ABDM_CLIENT_SECRET: str = ""
    ABDM_ENV: str = "sandbox"  # sandbox | production (selects base URL + X-CM-ID)
    ABDM_DRUG_REGISTRY_BASE_URL: str = ""  # override; else derived from ABDM_ENV

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
    # Gemini 2.5 models are "thinking" models: they reason before answering,
    # which roughly doubles latency and (on the streaming Smart Report / insight
    # path, where cloud output is fetched whole then burst as tokens) leaves the
    # UI on "generating" with no token progress for the entire call. Disabling
    # thinking (thinkingBudget=0) makes responses deterministic and ~2x faster —
    # the Gemini equivalent of OLLAMA_SUPPRESS_THINK. Reversible without a rebuild.
    GEMINI_SUPPRESS_THINK: bool = True

    # Storage
    STORAGE_PATH: str = "./data/attachments"
    STORAGE_BACKEND: str = "local"
    # PDF optimization on ingest (ghostscript image downsampling). Lossy —
    # embedded images are downsampled per PDF_OPTIMIZE_DPI. No-op if gs missing.
    OPTIMIZE_PDFS: bool = True
    PDF_OPTIMIZE_DPI: str = "ebook"  # screen(72) | ebook(150) | printer(300) | prepress

    # Desktop mode (Tauri sidecar): serve the built frontend SPA from the
    # backend itself so the webview loads the app same-origin
    # (http://127.0.0.1:<port>) and the httpOnly auth cookies stay first-party
    # (they can't be Secure over plain HTTP, so same-origin is required). Off by
    # default — the server .deb keeps using Caddy for static serving. When frozen
    # with PyInstaller, FRONTEND_DIST is ignored and the dist is read from
    # sys._MEIPASS/frontend (see the mount in app/main.py).
    SERVE_FRONTEND: bool = False
    FRONTEND_DIST: str = ""

    # AI Verification
    AI_VERIFICATION_ENABLED: bool = True
    # Run the second-model check synchronously (inline, before the response is
    # finalized so its status always ships with the content). When False, fall
    # back to the older fire-and-forget background check (status arrives later).
    AI_VERIFICATION_SYNCHRONOUS: bool = True
    # Validator selection: prefer a cloud provider from a DIFFERENT family than
    # the generator, and only use local Ollama as validator when no cloud
    # candidate is available (never Ollama-validating-Ollama).
    AI_VALIDATOR_CLOUD_PREFERRED: bool = True
    # Preferred validator family: when set (default "gemini"), the second-model
    # validator tries this family first within the cloud group, regardless of
    # provider order — so Groq-generated content is validated by Google even if
    # OpenRouter/OpenAI sit earlier in a household's list. Empty = honor order.
    AI_VALIDATOR_PREFERRED_FAMILY: str = "gemini"
    # Dynamic task router: when on, AI calls declare a task type and the router
    # (app/services/ai/task_router.py) picks the cheapest model meeting the task's
    # accuracy floor, escalating on low confidence. Off = today's ordered_providers.
    AI_ROUTER_ENABLED: bool = True
    AI_ROUTER_ESCALATION_ENABLED: bool = True
    # Result confidence below which a non-streaming task retries on a stronger
    # model. extraction_confidence maps high=1.0 / medium=0.5 / low=0.25 / none=0.0;
    # 0.3 escalates only clearly-low-confidence (data-present) results, not medium.
    AI_ROUTER_CONFIDENCE_THRESHOLD: float = 0.3

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
            # A dedicated at-rest ENCRYPTION_KEY is mandatory in production. The
            # empty-string default falls back to a SECRET_KEY-derived Fernet —
            # that conflates JWT-signing with file/secret encryption and means a
            # JWT-key rotation (or a restored DB on fresh hardware without the
            # key) bricks every encrypted attachment/2FA secret. The .deb postinst
            # generates it; refuse to boot without it so the gap can't ship.
            if not self.ENCRYPTION_KEY:
                raise ValueError(
                    "ENCRYPTION_KEY must be set in production! "
                    'Generate one with: '
                    '"python -c \'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\'"'
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
