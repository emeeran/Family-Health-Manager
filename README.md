# Family Health Manager

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-009688.svg)
![React](https://img.shields.io/badge/React-19-61DAFB.svg)
![Status](https://img.shields.io/badge/status-self--hosted-success)

A **self-hosted, privacy-first family health record manager**. Upload medical
documents — prescriptions, lab reports, discharge summaries — and let on-device
AI extract structured data. Track medications, vaccinations, and lab results;
review smart reports and drug-interaction checks; and ask questions about your
family's health history in a private chat. All on hardware you control.

Your health data never leaves your machine unless you explicitly configure a
cloud AI provider.

## ✨ Features

- **AI document extraction** — privacy-first via [Ollama](https://ollama.com)
  (local, default), with automatic cloud failover (OpenAI, Gemini, Groq,
  OpenRouter) when you add a key. Adding any cloud key makes extraction ~30–60×
  faster (cloud ~1–2s/doc vs CPU Ollama ~1–2min) with no other config.
- **Structured health records** — medications, vaccinations, lab results, vitals,
  and consultations, organised per family member.
- **Smart reports & insights** — health scores, abnormal-value flags, drug
  interaction checks, and preventive-care reminders.
- **Conversational Q&A** — a private chat assistant grounded in your records.
- **Encryption at rest** — files and 2FA secrets encrypted with Fernet, using a
  dedicated key kept separate from JWT signing.
- **Secure auth** — JWT access/refresh rotation with replay detection and
  optional TOTP two-factor authentication.
- **Backup & restore** — scheduled, encrypted database backups with one-click
  restore.
- **One-command deploy** — Debian `.deb` package with systemd + Caddy.

## 📸 Screenshots

<!-- Add 2–3 screenshots here (dashboard, record extraction, chat), e.g. -->
<!-- <img src="docs/screenshots/dashboard.png" width="600" alt="Dashboard" /> -->

## 🚀 Quick Start

```bash
git clone <repo-url> health-manager && cd health-manager
cp backend/.env.example backend/.env     # then generate a SECRET_KEY
./dev.sh                                   # backend (:8000) + frontend (:3000)
```

`dev.sh` picks the next free port from `:8000` (backend) and `:3000` (frontend)
and sources `backend/.env` for secrets. The Vite dev proxy forwards `/api` to the
backend, so no CORS config is needed in dev.

```bash
cd backend && uv run pytest     # backend tests
cd frontend && npm test         # frontend tests (vitest)
```

## ⚙️ Configuration

All settings are environment variables documented in
[`backend/.env.example`](backend/.env.example). The most important:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing key (required). |
| `ENCRYPTION_KEY` | Fernet key for files/2FA at rest (required in production). |
| `HEALTH_CHECK_SECRET` | Protects `GET /health/detail` (required in production). |
| `OLLAMA_MODEL` | Local AI model — must match `ollama list` (default `qwen3:4b`). |
| `DATABASE_URL` | SQLite (dev) or PostgreSQL (prod). |
| `APP_ENV=production` | Enables hardening: DEBUG off, secrets required. |
| `EXTRACTION_*` / `OLLAMA_KEEP_ALIVE` | Extraction perf knobs (timeouts, multi-image batch size, model warmup). See [`docs/07-deployment/deployment.md`](docs/07-deployment/deployment.md) → *Performance tuning*. |

## 📦 Deployment

Production is delivered as a Debian package behind Caddy + systemd.

```bash
bash packaging/build-deb.sh        # build the .deb
sudo dpkg -i health-manager_*.deb  # install (generates secrets, enables services)
```

See [`docs/07-deployment/`](docs/07-deployment/) for the full deployment guide.

## 🔒 Security

This application stores sensitive personal health information. Read
[`SECURITY.md`](SECURITY.md) for the threat model and vulnerability-reporting
policy. Highlights: Fernet encryption at rest, JWT + TOTP authentication, rate
limiting, and a hardened systemd unit (`NoNewPrivileges`, `ProtectSystem=strict`).

## 📚 Documentation

- [`CLAUDE.md`](CLAUDE.md) — engineering context & conventions
- [`docs/`](docs/) — SDD artefacts: domain, requirements, spec, design, ADRs
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- [`CHANGELOG.md`](CHANGELOG.md) — release history
- **API reference**: `/docs` (Swagger UI) when running locally

## 🛠 Tech Stack

| Layer     | Technology                              |
|-----------|-----------------------------------------|
| Frontend  | React 19, Vite, SWR, shadcn/ui          |
| Backend   | Python 3.11+, FastAPI, Pydantic v2      |
| Database  | SQLite (dev) / PostgreSQL (prod)        |
| AI        | Ollama (MedGemma) + cloud fallbacks     |
| Packaging | `uv` (Python) · Debian `.deb` (deploy)  |
| Testing   | pytest, httpx · vitest, Playwright      |
| Linting   | ruff, mypy · eslint, tsc                |

## 📁 Project Layout

| Path          | Contents                                                |
|---------------|---------------------------------------------------------|
| `backend/`    | FastAPI app, ORM models, services, tests                |
| `frontend/`   | React/Vite SPA                                          |
| `docs/`       | SDD artefacts (domain, requirements, spec, design)      |
| `prompts/`    | Prompt templates for the AI extraction pipeline         |
| `packaging/`  | Debian package, Caddyfile, systemd unit, deploy scripts |
| `scripts/`    | Deploy & sync helper scripts (gitignored)               |

## 🧪 SDD Pipeline

The Makefile drives spec-driven-development phases; artefacts land in `docs/`.

| Phase | Command            | Output                                  |
|-------|--------------------|-----------------------------------------|
| 0     | `make domain`      | `docs/00-domain/DOMAIN.md`              |
| 1     | `make reqs`        | `docs/01-requirements/REQUIREMENTS.md`  |
| 2     | `make spec`        | `docs/02-spec/SPEC.md`                  |
| 3     | `make review`      | `docs/03-review/REVIEW.md` (gate)       |
| 4     | `make design`      | `docs/04-design/DESIGN.md`              |
| 5     | `make code`        | `backend/app/`                          |
| 5.5   | `make review-code` | Bloat report (auto-fix)                 |
| 6     | `make test`        | Test results + coverage                 |

Run `make help` for the full list of targets.

## 🤝 Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup,
branching, commit, and review conventions. Please do not commit secrets.

## 📄 License

[MIT](LICENSE) © Meeran and contributors.
