# Deployment Guide

Family Health Manager ships as a **self-hosted Debian package (`.deb`)** running on
a single host: **systemd** services fronted by **Caddy**, backed by **SQLite**
(WAL mode). This document describes that real deployment path.

> The earlier Docker-Compose/PostgreSQL instructions were aspirational and did
> not match the shipping packaging. PostgreSQL remains a possible future backend
> but is **not** validated or supported by the packaged restore path today.

## Architecture

```
 browser ──► Caddy (:8080, TLS-terminator) ──► uvicorn 127.0.0.1:8000 (FastAPI)
                       │                              │
                       └─ serves built frontend      ├─ SQLite: /var/lib/health-manager/data/health.db
                                                      ├─ attachments: …/data/attachments/
                                                      ├─ backups: …/data/backups/
                                                      └─ Ollama (local AI) on :11434
```

systemd units (installed by the `.deb`):

| Unit | Role |
|------|------|
| `health-manager.service` | The FastAPI backend (uvicorn). Runs migrations via `ExecStartPre`. |
| `health-manager-caddy.service` | Caddy reverse proxy + static frontend. |
| `health-manager-restore.path` | Watches for a restore request and triggers `restore-archive.sh` as root. |

## Install

```bash
sudo apt install ./health-manager_<ver>_amd64.deb
# (a bare `dpkg -i` also works — postinst installs missing deps defensively)
```

The postinstall step creates the `health-manager` system user, the data/log
directories, generates secrets (see below), enables + starts the services, and
enables the restore path unit.

## Configuration

Edit `/etc/health-manager/config.env`, then `sudo systemctl restart health-manager`.
Secrets marked **auto-generated** are filled in on first install (and on upgrade
if missing).

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_ENV` | yes | `production` (shipped default). Forces `DEBUG=false`, disables OpenAPI docs, requires `HEALTH_CHECK_SECRET`. |
| `SECRET_KEY` | **auto** | JWT signing key. |
| `ENCRYPTION_KEY` | **auto** | Fernet key for files + 2FA secrets at rest (decoupled from `SECRET_KEY`). **Back it up — losing it makes encrypted files unrecoverable.** |
| `HEALTH_CHECK_SECRET` | **auto** | Shared secret for `/health/detail`. Required in production. |
| `DATABASE_URL` | no | SQLite default. (PostgreSQL is not validated for this path.) |
| `CORS_ORIGINS` | no | Comma-separated allowed origins. |
| `REDIS_URL` | no | Empty = in-memory fallback. Set this if you raise the worker count (see below). |
| `LOG_LEVEL` | no | `WARNING` (default) / `INFO` / `DEBUG`. |
| `RATE_LIMIT_*` / `AUTH_RATE_LIMIT_*` | no | 100/min general, 10/min for all `/auth/*` endpoints. |
| `OLLAMA_LOCAL_URL` / `OLLAMA_MODEL` | no | Local AI. Model must be `ollama pull`ed; pin the tag. |

## Health checks

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | none | **Liveness** — process is up (no dependency checks). |
| `GET /health/ready` | none | **Readiness** — pings the DB (`SELECT 1`); 503 if unreachable. Use for uptime monitors / load balancers. |
| `GET /health/detail` | `x-health-key` header | DB + disk + Ollama status. |

## Backups (automatic)

The in-process scheduler (`app/core/jobs.py`, single-instance via an `flock`) runs
a backup job that uses the SQLite **online-backup API** and tars `health.db` +
`attachments/` into:

```
/var/lib/health-manager/data/backups/backup_YYYYMMDD_HHMMSS.tar.gz
```

Retention is 30 days. Backups are encrypted at rest (attachments already are;
the DB snapshot is whatever the DB contains). **Backups live on the same disk as
the DB** — copy them off-host regularly (e.g. nightly `rsync` to NAS/cloud).

## Restore runbook

Restore is privileged (it must stop the app and swap the DB), so the app — which
runs unprivileged — cannot do it directly. Instead it (or an operator) writes the
target archive name to a flag file, and a systemd **path unit** runs
`/opt/health-manager/restore-archive.sh` as root.

**Trigger a restore (preferred — from the app's backup/restore UI):** the app
writes the archive name to the flag file; the path unit does the rest.

**Trigger a restore manually:**

```bash
# 1. Pick the archive to restore (must match backup_YYYYMMDD_HHMMSS.tar.gz):
ls /var/lib/health-manager/data/backups/

# 2. Write its name to the request flag (the path unit picks it up):
echo "backup_20260622_120000.tar.gz" | sudo tee /var/lib/health-manager/data/.restore-request

# 3. Watch the result marker (written atomically when the script finishes):
sudo cat /var/lib/health-manager/data/.restore-result
#   {"status":"ok","archive":"backup_20260622_120000.tar.gz","pre_restore_backup":"backup_prerestore_…tar.gz", …}
```

What the script does, in order:

1. Strictly re-validates the archive name (`backup_YYYYMMDD_HHMMSS.tar.gz` — no
   path separators/traversal) and that the tar contains `health.db` (PostgreSQL
   dumps are rejected with a clear error).
2. Makes a **safety backup** of the *current* state → `backup_prerestore_*.tar.gz`
   (this is the undo path if the restore is wrong).
3. Stops the app, swaps `health.db` (+ `-wal`/`-shm` dropped) and `attachments/`.
4. Restarts the app — `ExecStartPre db-setup.py` runs `alembic upgrade head` so
   an older snapshot is migrated forward automatically.
5. Writes the JSON result marker and removes the request flag.

**Recover from a bad restore:** restore the `backup_prerestore_*.tar.gz` the
script created in step 2, using the same mechanism.

> The script is exercised end-to-end by `backend/tests/test_restore_archive.py`
> (via env overrides) — run it after any change to `restore-archive.sh`.

## Logs

```bash
sudo journalctl -u health-manager.service -f
```

Structured JSON in production (if `python-json-logger` is installed). Raise
verbosity without a rebuild via `LOG_LEVEL=INFO` (or `DEBUG`) in `config.env`,
then restart.

## Workers & Redis

The default is **1 uvicorn worker**. Async I/O handles concurrency and the heavy
AI work runs in a separate Ollama process, so a single worker is usually enough.
If you raise `--workers` in the unit file, **set `REDIS_URL`** — otherwise rate
limiting and the insight cache use per-process in-memory state and diverge across
workers.

## Performance tuning (document extraction)

Extraction is **LLM-bound**: app-side work is ~0.1 ms, the model call dominates by
orders of magnitude (cloud ~1–2 s/doc, CPU Ollama ~1–2 min/doc). So the levers are
*provider reliability*, *LLM-call count*, and *perceived latency* — not the Python
pipeline. Relevant settings live in `/etc/health-manager/config.env` (edit, then
`sudo systemctl restart health-manager`):

| Setting | Default | What it does |
|---------|---------|--------------|
| provider `primary` | `auto` | Per-household (Settings UI). Cloud-first when any cloud key is set, else local. Adding a cloud key is the single biggest speedup (~30–60×). |
| `OLLAMA_KEEP_ALIVE` | `30m` | Keeps the model resident between extractions so back-to-back jobs skip the ~9 s CPU cold-load. Costs ~3 GB RAM while alive. |
| `OLLAMA_WARMUP_ON_STARTUP` | `true` | Loads the model once at boot so the *first* extraction isn't cold. |
| `EXTRACTION_PROVIDER_TIMEOUT` | `15` | Seconds before a dead/slow **cloud** key is abandoned and the next provider tried. |
| `EXTRACTION_LOCAL_TIMEOUT` | `300` | Wall-clock cap for the **local** Ollama path (bounds a stuck generation). |
| `EXTRACTION_PAGES_PER_CHUNK` | `5` | OCR pages packed into one extraction call (larger = fewer calls on multi-page scans). |
| `EXTRACTION_VISION_BATCH_SIZE` | `3` | Page images per multi-image vision call (a 9-page scan → 3 calls, was 9). |
| `EXTRACTION_RACE_PROVIDERS` | `false` | Race healthy cloud providers in parallel. Off by default — the pre-flight probe already prunes dead keys. |
| `OLLAMA_FAST_MODEL` | _empty_ | Faster/smaller model for clean-text extraction. **Eval-gated** — validate accuracy before enabling. |

A few behaviours need no setting:

- **Pre-flight provider probe.** Each extraction first probes providers in parallel
  (60 s cache, shared with `/ai/status`) and prunes confirmed-dead ones, so a dead
  key no longer costs 15 s of failover per provider.
- **Extraction cache.** Results are cached by file hash + provider fingerprint for
  7 days (positives) / 10 min (genuinely-empty negatives). Re-uploads and retries
  of the same file are instant.
- **Live progress.** `/extract/stream` emits `{stage:"progress", pct, detail}`
  events (OCR / chunk / vision-batch / transcription) plus a provider-health line.

**"Stuck at 45%" / slow extraction** is almost always provider-bound, not the app.
Open **Settings → AI Status** (or `GET /api/v1/ai/status`): dead cloud keys (401 /
402 / model-404) are the usual cause — fix or remove the key, or add a Groq key
(free tier) for fast cloud extraction. The probe + log line
`extraction … provider=… cache=hit/miss elapsed_ms=…` (`LOG_LEVEL=INFO`) confirm
which provider served each extraction.

## Local development

```bash
./dev.sh                      # backend (:8001, --reload) + frontend (:3000, Vite proxy)
cd backend && uv run pytest   # tests
```

Dev uses `backend/.env` (gitignored) and `APP_ENV=development`; it is entirely
separate from the packaged `/etc/health-manager/config.env`.

## Database migrations

- **Packaged install:** migrations run automatically on every start via the
  unit's `ExecStartPre` (`db-setup.py` → `alembic upgrade head`). No manual step.
- The migration baseline is a single squashed `create_all`; new schema changes
  must add **new** Alembic revisions on top of it (don't edit the baseline — its
  reused revision id is what makes `alembic upgrade head` a no-op on existing
  stamped databases).
