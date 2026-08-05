# Family Health Manager — User Manual

A self-hosted, privacy-first family health record manager with AI-powered
document extraction, medication tracking, and conversational health Q&A.

This manual covers **installation, the main workflows, configuration, the API
contract, testing, and troubleshooting**. It describes the current code only.
The interactive API reference (`/docs`, Swagger UI) is available whenever the
backend is running in development.

There are **three ways to run the app**, all built from the same code:

| Build | Package | Runs as | Best for |
|-------|---------|---------|----------|
| **Dev** | source (`./dev.sh`) | two processes (uvicorn + Vite) | development |
| **Server** | `health-manager_*.deb` | systemd services behind Caddy | always-on hosting |
| **Desktop** | `health-manager-desktop_*.deb` | a Tauri window + sidecar | single-user, native app |

---

## 1. Requirements

- **OS:** Ubuntu 24.x (or similar Debian-leaning Linux). The desktop build is
  Linux-only.
- **Python:** 3.11+ (managed with [`uv`](https://docs.astral.sh/uv/), never pip).
- **Node.js:** 20+ for the frontend.
- **Rust + Tauri CLI 2.x:** only for building the desktop `.deb`.
- **AI (optional but recommended):** [Ollama](https://ollama.com) for fully
  local AI, **or** a cloud provider key (Groq / Google Gemini / OpenRouter /
  OpenAI). With none configured, AI features degrade gracefully (empty results).

---

## 2. Installation

### 2.1 Development (from source)

```bash
# 1. Get the code
git clone https://github.com/emeeran/Family-Health-Manager.git health-manager
cd health-manager

# 2. Create your local env from the template and generate a secret
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into SECRET_KEY

# 3. (Optional) local AI model — must match OLLAMA_MODEL (default qwen3:4b)
ollama pull qwen3:4b

# 4. Start backend (:8000) + frontend (:3000)
./dev.sh
```

`dev.sh` picks the next free port from `:8000` (backend) and `:3000` (frontend),
sources `backend/.env` for secrets, and starts both processes. The Vite dev proxy
forwards `/api` to the backend, so **no CORS configuration is needed in dev**.

Open <http://localhost:3000> and register your first (admin) account.

### 2.2 Server `.deb` (always-on hosting)

```bash
bash packaging/build-deb.sh          # build the server .deb
sudo dpkg -i health-manager_*.deb    # install (generates secrets, enables services)
```

The install generates `SECRET_KEY` / `ENCRYPTION_KEY` / `HEALTH_CHECK_SECRET`,
enables the `health-manager` (backend) and Caddy services, and runs DB setup.
Behind Caddy + systemd; data lives under `/var/lib/health-manager/data/`.
Full guide: [`docs/07-deployment/deployment.md`](docs/07-deployment/deployment.md).

### 2.3 Desktop `.deb` (native app)

```bash
bash packaging/build-desktop-deb.sh                 # build the desktop .deb
sudo apt install ./health-manager-desktop_*.deb     # install (resolves runtime deps)
```

Launch **"Health Manager"** from your application menu (or run
`health-manager-desktop`). It spawns a PyInstaller-frozen backend on a local
`127.0.0.1` port and serves the SPA same-origin. Per-user data lives under
`~/.local/share/com.dawnstar.healthmanager/`. Details:
[`packaging/README-desktop.md`](packaging/README-desktop.md).

---

## 3. First-run setup

1. **Register** the admin account (first signup becomes the household admin).
2. **Onboarding** — name your household and add family **members** (name, DOB,
   relationship, blood group, allergies).
3. **AI providers** — open **Settings → AI Providers**. With nothing configured,
   AI features return empty. Options:
   - **Local (Ollama):** pull a model (`ollama pull qwen3:4b`). The desktop app
     auto-starts `ollama serve` if installed.
   - **Cloud:** paste a key for Groq / Google Gemini / OpenRouter / OpenAI. The
     household "primary provider" is **`auto`** by default — cloud-first when any
     key is set, else local — so adding a key is all it takes to go ~30–60×
     faster.
   - **Google Gemini zero-config (ADC):** if you've run
     `gcloud auth application-default login`, the app auto-detects the standard
     gcloud credentials and infers the Vertex project — no key or `.env` needed.
4. **Optional security** — enable TOTP two-factor auth on your account.

---

## 4. Main workflows

### 4.1 Upload & extract a document

1. Open a member → **Add record** (or the batch uploader).
2. Upload a prescription, lab report, or discharge summary (PDF / image).
3. The app runs **AI extraction** with live per-stage progress and auto-fills the
   record (medications, labs, vitals, dates). You review and save.
4. Every AI extraction is **checked by a second model**; disputed values surface
   a ⚠ marker.

Without a working AI provider, the upload still saves — but fields stay empty.

### 4.2 Manage health data

Per member, track **medications, vaccinations, lab results, vitals, providers
(doctors/labs), reminders, and consultations**. Records support a timeline view,
duplicate detection + merge, and editing. Uploaded files are stored encrypted at
rest.

### 4.3 Smart reports & insights

- **Smart Report** — a streamed AI overview of the member's health (health
  score, chronic conditions, abnormal labs, trends). Comprehensive mode analyzes
  the full history (up to 100 records).
- **Health Assessment**, **Medication Report** (structured medicine cards +
  interactions + safety alerts), and **pre-consultation notes**.
- Reports carry **provenance** (which source records they're built from) and a
  freshness date — never derived from LLM output.
- **Export to PDF** — opens a native Save-As dialog in the desktop app; the
  browser/dev path downloads a PDF.

### 4.4 Drug info & interactions

For a member's medications: **FDA recalls, prescribing labels, adverse events,
substitutes, indications**, and **drug–drug interaction checks**. Drug lookup is
local-catalog-first (curated Indian brand catalog if seeded), then ABDM / openFDA
/ RxNorm, with AI as a verified fallback (prefers "no data" over "wrong drug").

### 4.5 Conversational Q&A

A private **chat assistant** grounded in your household's records. Each answer is
validated by a second model; streaming responses render as they arrive.

### 4.6 Backup & restore

- **Export** a portable, encrypted archive of the whole household.
- **Validate** before import, then **Import** into another install.
- On the server build, admins can list/download/restore server-side archives;
  restore is applied via a systemd path unit and restarts both the backend and
  Caddy.

---

## 5. Configuration reference

All settings are environment variables; the canonical, commented list is
[`backend/.env.example`](backend/.env.example). Highlights:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | JWT signing key (required). | — |
| `ENCRYPTION_KEY` | Fernet key for files/2FA at rest. Empty in dev (auto-derived); **required in prod**. | `""` |
| `HEALTH_CHECK_SECRET` | Protects `GET /health/detail`. **Required in prod.** | `""` |
| `APP_ENV` | `production` hardens: DEBUG off, secrets required, `/docs` disabled, JSON logs. | `development` |
| `DATABASE_URL` | SQLite (dev) or PostgreSQL (prod). | `sqlite+aiosqlite:///./data/health.db` |
| `CORS_ORIGINS` | Comma-separated allowed origins. | `http://localhost:3000` |
| `OLLAMA_LOCAL_URL` | Ollama base URL (must include `http://`). | `http://localhost:11434` |
| `OLLAMA_MODEL` / `OLLAMA_TEXT_MODEL` | Local model — must match `ollama list`. | `qwen3:4b` |
| `OLLAMA_KEEP_ALIVE` | How long Ollama keeps the model resident. | `30m` |
| `OLLAMA_WARMUP_ON_STARTUP` | Warm the model at boot so the first extraction isn't cold. | `true` |
| `EXTRACTION_PROVIDER_TIMEOUT` | Cloud provider call abandoned after this (dead/slow key → next). | `15` |
| `EXTRACTION_LOCAL_TIMEOUT` | Local Ollama call timeout (CPU is slow). | `300` |
| `EXTRACTION_RACE_PROVIDERS` | Race healthy cloud providers in parallel (off = sequential failover). | `false` |
| `EXTRACTION_PAGES_PER_CHUNK` | OCR pages packed into one extraction call. | `5` |
| `EXTRACTION_VISION_BATCH_SIZE` | Page images per multi-image vision call (1 = legacy). | `3` |
| `EXTRACTION_VISION_MAX_DIM` | Longest-side px cap on uploaded images before vision. | `1568` |
| `EXTRACTION_MAX_TOKENS` | Soft token cap for cloud extraction calls. | `4096` |

The household AI provider order and the Cloud/Local primary toggle are set
per-household in **Settings → AI Providers**, not via env vars.

Performance-tuning narrative: [`docs/07-deployment/deployment.md`](docs/07-deployment/deployment.md)
→ *Performance tuning*.

---

## 6. API / JSON contract

All routes are under `/api/v1`. While running in dev, browse the full schema at
**<http://localhost:8000/docs>** (Swagger UI; disabled when `APP_ENV=production`).
Feature areas (selected):

- **Auth** — `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`,
  `/auth/me`, `/auth/change-password`, `/auth/2fa/*`, `/auth/login/2fa`.
- **Household** — `/household`, `/household/settings`, `/household/ai-provider-config`.
- **Members & records** — `/members`, `/members/{id}/records`,
  `/members/{id}/records/extract` (and `/extract/stream` for live progress),
  `/records/timeline/list`, `/records/dedup` + `/merge`.
- **AI** — `/ai/insights`, `/ai/explain`, `/ai/status`, `/ai/extraction-metrics`.
- **Medications / vaccinations** — `/members/{id}/medications*`, `/vaccinations`.
- **Drug info & interactions** — `/members/{id}/drug-recalls`, `/drug-label`,
  `/drug-adverse-events`, `/drug-substitutes`, `/drug-indication`,
  `/members/{id}/drug-interactions`.
- **Reports** — smart report, health assessment, medication report,
  pre-consultation, preventive care, resources.
- **Conversations** — `/conversations` (chat).
- **Backup** — `/backup/export`, `/backup/validate`, `/backup/import`,
  `/backup/run` (admin), `/backup/archives`, `/backup/archives/{name}/restore`.
- **Dashboard** — `/dashboard/summary`, `/dashboard/member-comparison`,
  `/dashboard/members/{id}/risk-assessment`.

**Streaming extraction** (`/extract/stream`) emits Server-Sent Events:

```
event: progress
data: {"stage":"progress","pct":42,"detail":"extracting labs …"}
```

followed by the final structured record. Authentication uses http-only JWT
cookies (access + refresh, with replay detection); the desktop app serves
same-origin over plain HTTP so the cookies work without TLS.

---

## 7. Testing, linting, and the SDD pipeline

```bash
# Backend
cd backend && uv run pytest                       # tests
cd backend && uv run ruff check --fix .           # lint + autofix
cd backend && uv run ruff format .                # format
cd backend && uv run mypy .                       # type-check

# Frontend
cd frontend && npm test                           # vitest unit tests
cd frontend && npm run test:e2e                   # playwright e2e
cd frontend && npm run lint                       # eslint
cd frontend && npm run format                     # prettier
```

Git hooks ([`lefthook.yml`](lefthook.yml)): pre-commit runs ruff + prettier;
pre-push runs mypy + `tsc`.

The Makefile drives spec-driven-development; artefacts land in `docs/`:

| Command | Output |
|---------|--------|
| `make domain` | `docs/00-domain/DOMAIN.md` |
| `make reqs` | `docs/01-requirements/REQUIREMENTS.md` |
| `make spec` | `docs/02-spec/SPEC.md` |
| `make review` | `docs/03-review/REVIEW.md` (gate) |
| `make design` | `docs/04-design/DESIGN.md` |
| `make code` | scaffold into `backend/app/` |
| `make review-code` | bloat report (auto-fix) |
| `make test` | test results + coverage |

Run `make help` for the full list.

---

## 8. Exit codes & CLI contract

- **`./dev.sh`** — exits non-zero if the backend or frontend fails to start.
- **`make <target>`** — exits non-zero if the underlying tool (pytest / ruff /
  mypy / tsc) fails; `make test` is the CI gate.
- **`pytest` / `ruff` / `mypy` / `tsc` / `eslint`** — standard Unix convention:
  `0` success, non-zero on failure.
- **The app itself** speaks HTTP: `200/201/204` success, `400` bad request,
  `401/403` auth/permission, `404` not found, `409` conflict (e.g. duplicate),
  `422` validation error, `429` rate-limited, `5xx` server error.

---

## 9. Logging

- The backend logs to stdout via uvicorn. In production (`APP_ENV=production`),
  logs are emitted as JSON (structured) when `python-json-logger` is available.
- Verbosity is controlled by `LOG_LEVEL` (`DEBUG`/`INFO`/`WARNING`/…). Note
  `LOG_LEVEL=WARNING` hides app INFO lines, which can make startup look silent —
  that is not a failure.
- Each extraction emits one structured line:
  `provider=… cache=hit|miss elapsed_ms=…`.
- The desktop app prints `[backend] …` lines to the terminal you launched it
  from — the first place to look when something's wrong.

---

## 10. Troubleshooting / FAQ

**AI fields come back empty / "record not auto-filled".**
No AI provider is reachable. Either `ollama pull qwen3:4b` (and make sure
`OLLAMA_LOCAL_URL` includes `http://`), or add a cloud key in
**Settings → AI Providers**. Inspect `/health/detail` (needs
`HEALTH_CHECK_SECRET`) to confirm provider health.

**Extraction is very slow (1–2 minutes per document).**
That's CPU-only Ollama. Add any cloud key — extraction becomes cloud-first
automatically and drops to ~1–2s/doc.

**Smart report / chat comes back blank.**
Often an exhausted or invalid API key (a dead-keyed Gemini, for example).
Switch provider or use Gemini-via-ADC (`gcloud auth application-default login`).

**"Network error / can't log in" on the installed server.**
The backend (or Caddy, on the server build) isn't running. Check
`systemctl status health-manager` and `systemctl status caddy`. A successful
restore must restart **both** services.

**Port 8000 is already in use.**
Another process is squatting it. `./dev.sh` auto-picks the next free port for
dev; for the installed server, free the port or move the service.

**Desktop window never appears / closes immediately.**
Launch from a terminal (`health-manager-desktop`) and read the `[backend]`
lines — usually a missing runtime library. A second launch just focuses the
existing single-instance window.

**How do I reset everything?**
- Desktop: quit the app and delete `~/.local/share/com.dawnstar.healthmanager/`.
- Dev: delete `backend/data/` (the SQLite DB + attachments).
- Server: admins can use **Reset database** in household admin, or drop the
  `/var/lib/health-manager/data/` directory (then restart the service).

**Where are my secrets?**
Dev: `backend/.env`. Desktop install: `~/.local/share/com.dawnstar.healthmanager/config.env`.
Server install: under `/opt/health-manager/` (generated at install). Never
commit any of these.

---

## 11. Documentation index

- [`README.md`](README.md) — project overview & quick start
- [`CLAUDE.md`](CLAUDE.md) — engineering context & conventions
- [`docs/`](docs/) — SDD artefacts (domain, requirements, spec, design, ADRs)
- [`docs/07-deployment/deployment.md`](docs/07-deployment/deployment.md) — server deployment guide
- [`packaging/README-desktop.md`](packaging/README-desktop.md) — desktop app guide
- [`CHANGELOG.md`](CHANGELOG.md) — release history
- [`SECURITY.md`](SECURITY.md) — threat model & reporting
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- **API reference**: `/docs` (Swagger UI) when running locally in dev

## License

[MIT](LICENSE) © Meeran and contributors.
