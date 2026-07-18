# Production Readiness Audit — 2026-07-18

## Summary
**Verdict: ready with fixes.** The app is functional, well-tested (476 backend tests),
and architecturally sound. The blockers below are real but bounded: an AsyncSession
concurrency bug, three observability gaps on critical paths, an FD-leak on shutdown,
an unprotected `main` branch, and plaintext API keys in `.env`. Addressing those six
makes the app production-safe. The high-severity items (silent failure modes in
extraction/DDI, stale `.env.example`, scheduler robustness) should follow before any
network-exposed deployment.

## Blockers (must fix before prod)

- [ ] **`member_service.py:533`, `dashboard.py:75`, `member_history.py:223`** — `asyncio.gather` runs multiple DB coroutines on the **same AsyncSession** (not concurrency-safe; raises `InvalidRequestError` under concurrent load). Fix: run serially or give each its own session.
- [ ] **`routers/auth.py` (entire file)** — login/register/2FA/refresh/logout are **completely unlogged** — no `logger.info` on success, no `logger.warning` on 401. Brute-force / credential-stuffing undetectable.
- [ ] **`services/ai/providers/{gemini,openrouter,groq}.py`** — each creates `logger = logging.getLogger(__name__)` but **never calls it**. Per-provider failure status/body lost; bad key indistinguishable from upstream outage.
- [ ] **`main.py:162-178`** — shutdown never `.aclose()` the 3 shared httpx clients (cloud/ollama/drug_info). FD leak on every SIGTERM; `ResourceWarning` in tests.
- [ ] **`.github/workflows/ci.yml` + branch protection** — CI runs, but **`main` has no branch-protection rules** (no required checks). Anyone can push/merge a broken build. CI can't actually block.
- [ ] **`backend/.env`** — real API keys (OpenAI/openFDA/Gemini/Groq/OpenRouter) in **plaintext on disk**. Gitignored (not in history) but any backup/zip/deb-package leaks them. Rotate + sanitise.

## High priority

- [ ] **`insight_generator.py:73-77`** — DDI JSON-parse failure silently → "no interactions found" (safety-critical green light with no log). Return a sentinel the UI can distinguish.
- [ ] **`routers/health_records.py:86-88`** — `/extract` swallows ALL failures → empty form, 200 OK, no signal that extraction failed. The streaming sibling emits an error event; the blocking path should too.
- [ ] **`services/ai/providers/openai.py:45-50`** — catches `except Exception` → continues to fallback. A 401/429/persistent-5xx silently degrades on every call with no operator signal.
- [ ] **`services/auth_service.py:37-44`** — open registration; **first user auto-admin** with no `ALLOW_REGISTRATION` gate. On a fresh/recent DB, attacker reaches endpoint → admin.
- [ ] **`config.py:76-77` vs `.env.example`** — `OLLAMA_MODEL="qwen3"` default, but `.env.example`/docs say `medgemma:4b`. Fresh deploy without env var → silent empty extraction (documented failure mode).
- [ ] **`.env.example` (whole file)** — stale: documents ~12 of ~40 Settings. Missing all external-API knobs (`DRUGBANK_API_KEY`, `OPENFDA_API_KEY`, `MEDLINEPLUS_CONNECT_URL`, `CLINICALTRIALS_BASE_URL`, `DAILYMED_BASE_URL`, `HEALTH_CANADA_DPD_URL`, `GOV_UK_SEARCH_URL`, `RXNORM_BASE_URL`) + `OLLAMA_TIMEOUT`, `MAX_*_SIZE_MB`, `RUN_SCHEDULER`, etc.
- [ ] **`config.py:40,110; scheduler.py:117`** — CWD-relative `./data/` paths. Running outside `backend/` splits DB/storage/scheduler state. Packaging papers over it; bare `uvicorn` doesn't.
- [ ] **`scheduler.py:39-61`** — fcntl guard **fail-open**: broad `except Exception` → runs unlocked. On overlayfs/shared-volume, two workers can both fire periodic jobs.
- [ ] **`scheduler.py:74-92`** — asyncio fallback has **no overlap guard** (unlike APScheduler's `max_instances=1`). Long jobs (backup, integrity scan) can pile up.
- [ ] **`main.py:415-432`** — `/health/ready` only probes DB, not Ollama or disk. LB routes to an instance where Ollama is down → silent extraction failures.
- [ ] **`ci.yml:34`** — `--cov-fail-under=40` is too permissive for a health-data app. Critical paths (auth, encryption, storage, dedup) deserve per-module gates or ≥70%.
- [ ] **`test_drug_info_providers.py` (entire file)** — external-API error/timeout paths untested (no `ConnectError`, `ReadTimeout`, or malformed-JSON test). Only happy/404 mocked.
- [ ] **`test_ollama_medgemma.py:25,41,120,175`** — Ollama integration tests skip in CI (no Ollama). Prod extraction path has no hermetic coverage; false-green.

## Medium / Low (selected — full list in subagent reports)

- [medium] `backup.py:73-93` — reads entire ZIP (up to 500 MB) into memory before size check. DoS vector; stream-validate from `Content-Length`.
- [medium] `backup_service.py:580-582` — no decompressed-size cap on restore; zip-bomb risk.
- [medium] `cache.py:88,106,128` — Redis errors swallowed silently with `pass` (no log). Redis outage invisible.
- [medium] `security.py:39,94` — JWT decode failures swallowed silently (tampered/expired tokens produce no audit signal).
- [medium] `auth_service.py:54-63` — username enumeration via timing (no constant-time dummy hash).
- [medium] `config.py:111` — `STORAGE_BACKEND` is dead config (never read).
- [medium] `config.py:125` — `DEBUG` field set but never read (real prod gating is `APP_ENV == "production"`).
- [medium] `core/provider_keys.py:80-98` — admin-settable Ollama URL is an SSRF surface (no scheme/host allowlist; could target `169.254.169.254`).
- [medium] `core/rate_limiter.py:33` — in-memory fallback prunes only at 10k entries; below that, IPs never expire (slow memory creep under NAT).
- [low] `drug_info/base.py:49-60` — no dead-event-loop guard (unlike `ai/base.py:170-186`). Post-fork reload can hang.
- [low] `encryption.py:48` — legacy Fernet key uses static salt (documented; acceptable until migration complete).
- [low] `frontend/smoke.mjs` — untracked scaffolding file; not wired to any test runner.
- [low] `test_chatbot_accuracy.py` — lives under `tests/` but has zero `test_` functions; script masquerading as test.

## Explicitly out of scope / accepted risk

- **12 broad `except Exception` in drug_info/health_resources providers** — intentional graceful-degradation (panels never 500 on upstream failure); each logs with `exc_info=True`. Evaluated in Phase 2; kept.
- **SQL injection / path traversal / shell injection / deserialization** — all verified clean by the security audit. ORM queries parameterised; storage path-validated; subprocess uses list args; no pickle/eval on untrusted input.
- **JWT / password hashing / cookie security** — HS256 + issuer/audience + jti revocation; argon2; httpOnly + SameSite=strict + secure-in-prod cookies. Solid.
- **Auth + household scoping on all new endpoints** — every `/members/{id}/drug-*`, `/drug-education`, `/clinical-trials`, `/canadian-product`, `/uk-alerts` requires `require_member_in_household` or `get_household_from_token`. Verified.
- **External API base URLs** — all hardcoded constants in `config.py` (not user-configurable) except Ollama (admin-settable — noted as medium SSRF above). No user-redirectable SSRF.

## Missed by pipeline, caught by blind review

The blind reviewer (sanitized, context-blind subagent — see `.pipeline/blind-review.md`)
found four issues that Phase 4's audit missed:

- [ ] **`health_records.py:764-778`** — background tasks fire before the request
  session commits (only `flush()`, not `commit()`). The correctness subagent
  verified line 902 was guarded but **missed lines 764-778** (a different code path).
  Matches the project's own documented landmine. One-line fix: `await db.commit()`
  before `background_tasks.add_task`.
- [ ] **`backup_service.py:63-158`** — encryption key (`ENCRYPTION_KEY`) is **not
  included in the backup archive**. Restore onto fresh hardware → DB and files that
  can't be decrypted. Every encrypted attachment, 2FA secret, and provider key
  permanently lost.
- [ ] **`frontend/package.json:3` vs `backend/app/core/config.py:22`** — frontend
  version (1.0.4) and backend version (1.1.1) have **drifted with no skew check**.
  Deploys can ship an API the UI doesn't speak.
- [ ] **`routers/auth.py:200-245`** — **2FA bypass via password reset**: sessions
  revoke but 2FA state isn't re-verified after reset. Combined with weak rate-limiting
  on auth endpoints, an attacker with a stolen password can force the reset flow and
  skip the second factor.

**Open question (disagreement):** The correctness subagent said the
background-task-commit race is "correctly handled at `health_records.py:902`."
The blind reviewer says it's still live at `health_records.py:764-778`. Both cite
real lines — these may be **different endpoints** (one guarded, one not). Needs
human verification of which paths still have the race.

## Both agree (higher confidence)

The blind reviewer independently corroborated these AUDIT.md findings, raising
confidence: DDI silent-failure (#1), `/health` readiness gap (#6/13), rate-limiter
not applied to routers (#7), static Fernet salt (#9), untested external-API error
paths, AI-parse returning empty silently (#17).

## Subagent reports
Full per-dimension findings are in the subagent outputs (correctness, security,
config, observability, testing/CI, ops). This document synthesizes and
deduplicates them. Blind review at `.pipeline/blind-review.md`.
