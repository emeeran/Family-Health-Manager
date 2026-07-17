# Building DAWNSTAR Family Health Keeper: A Self-Hosted Health Record Manager

Managing health records has become increasingly challenging, particularly for those caring for elderly family members with chronic conditions or young children who require frequent doctor visits. Between tracking prescriptions and organizing lab reports, maintaining these records and accessing them when needed can quickly become overwhelming. For some time, I have been planning to develop an application for managing my family's medical records. Finally built this app.

## The Goal

I needed a system that could:

- **Centralize medical documents** — prescriptions, lab reports, discharge summaries, consultation notes — in one place, organized per family member.
- **Extract structured data automatically** — instead of manually typing up details from every doctor visit, the app should read uploaded documents and populate records on its own.
- **Track ongoing care** — active medications, vaccination schedules, upcoming appointments, and refill reminders.
- **Surface insights** — flag abnormal lab values, check for drug interactions, compute health scores, and nudge toward preventive care.
- **Let me ask questions** — a conversational assistant that can answer questions like "When did my mother last have her blood work done?" or "Is there any interaction between her current medications?"
- **Keep data private** — health data is the most sensitive information a family owns. It should live on hardware I control, not in a third-party cloud.
- **Be deployable without a PhD** — one command to install, one command to back up.

## The Solution

**DAWNSTAR Family Health Keeper** is a self-hosted, privacy-first family health record manager that checks every box above.

**Document extraction is AI-powered and local-first.** You drag and drop a prescription PDF or lab report, and the app uses [Ollama](https://ollama.com) running on your own machine (with MedGemma by default) to extract structured data — medications, dosages, lab values, diagnoses, follow-up dates. No data leaves your machine. If you don't have a capable GPU, you can optionally configure cloud providers (OpenAI, Gemini, Groq, OpenRouter) as fallbacks — but that's entirely your choice.

**Records are structured, not just file dumps.** Each family member has a profile with their conditions, allergies, vitals, and care providers. Health records link to specific members and providers, capturing clinical data, prescriptions, diagnoses, and summaries. Medications, vaccinations, and lab results are tracked as first-class entities with their own timelines.

**Smart reports do the analysis for you.** The app computes a health score broken down by category (BMI, condition management, medication adherence, visit recency, lab result trends). It flags abnormal lab values against reference ranges, checks for drug interactions between a member's active medications, and generates preventive-care reminders based on age and conditions.

**A private chat assistant is grounded in your records.** You can ask questions in natural language and get answers based on your family's actual health history — not generic web search results. The assistant builds context from your records before forwarding the question to the AI model.

**Security is baked in, not bolted on.** Files and 2FA secrets are encrypted at rest with Fernet (streaming encryption in 64 KB chunks). Authentication uses JWT access/refresh token rotation with replay detection and optional TOTP two-factor auth. The production systemd unit runs with `NoNewPrivileges` and `ProtectSystem=strict`.

**Backup and restore are first-class.** Scheduled, encrypted database backups happen automatically, and one-click restore means you're never one disk failure away from losing everything.

## How It Works

The app is a classic two-tier architecture designed for single-server self-hosting:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  React SPA  │────▶│  FastAPI     │────▶│  SQLite / PG    │
│  (Vite)     │ /api│  Backend     │     │  Database       │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
                    ┌──────▼───────┐
                    │  Ollama      │  (local AI — MedGemma)
                    │  + fallbacks │  (OpenAI / Gemini / Groq / OpenRouter)
                    └──────────────┘
```

**Frontend** — A React 19 single-page application built with Vite, using SWR for data fetching and shadcn/ui for the component library. Pages cover member profiles, record management (create/edit/batch upload), provider directories, AI tools (document extraction, drug interactions, insights, pre-consultation summaries, chat), reminders, and settings. The Vite dev proxy forwards `/api` calls to the backend so no CORS configuration is needed during development.

**Backend** — A Python 3.11+ FastAPI application with Pydantic v2 for validation. The codebase is organized into clean layers:

- **Routers** — 28 route modules covering auth, members, health records, medications, vaccinations, lab results, providers, AI tools, conversations, reminders, backups, and system health.
- **Services** — Business logic separated from HTTP concerns: a multi-provider AI service with circuit breaker failover, health score computation, lab result analysis, drug interaction checking, preventive care recommendations, and encrypted backup scheduling.
- **Models** — SQLAlchemy ORM models for 18 entities (users, households, family members, health records, medications, vaccinations, lab results, providers, attachments, reminders, health alerts, conversations, AI transactions, and auth tokens).
- **Core** — Configuration, database sessions, Fernet encryption at rest, content-addressable file storage with deduplication, and thumbnail generation for images and PDFs.

**AI pipeline** — The AI layer is the most architecturally interesting piece. A base service defines the provider interface, and five providers implement it (Ollama, OpenAI, Gemini, Groq, OpenRouter). A circuit breaker tracks consecutive failures per provider — after three failures, the circuit opens and that provider is skipped for a 60-second cooldown. This means if Ollama is slow or down, requests automatically failover to the next configured cloud provider without manual intervention. The pipeline includes a document extractor for structured data extraction, a context builder that assembles relevant medical history for the chat assistant, and an insight generator for health reports.

**Storage** — Files (uploaded documents, thumbnails) are stored using content-addressable storage with SHA-256 deduplication, encrypted at rest with Fernet in streaming 64 KB chunks. The database is SQLite for development and PostgreSQL for production.

**Deployment** — The entire app ships as a Debian `.deb` package. Running `dpkg -i` generates encryption keys, enables systemd services, and configures Caddy as a reverse proxy with automatic HTTPS. The systemd unit is hardened with `NoNewPrivileges`, `ProtectSystem=strict`, and `PrivateTmp`.

---

The result is something I actually use every day. My mother's prescriptions, my father's lab reports, my daughter's vaccination schedule — all in one place, searchable, and backed up. The AI extraction saves me from typing up every visit, and the chat assistant means I never have to dig through a folder at 11 PM to find when a medication was last changed. It's not a SaaS — it's mine, and that's the point.

The code is [available on GitHub](https://github.com/) under the MIT license. Feedback and contributions welcome.
