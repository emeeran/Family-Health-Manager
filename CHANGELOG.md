# Changelog

All notable changes to **Family Health Manager** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.9] - 2026-07-20

### Fixed
- A successful restore left the web server down, so the site was unreachable
  ("Network error. Check your connection." / can't log in). The Caddy unit has
  `Requires=health-manager.service`, so stopping the backend during a restore
  also stops Caddy — but the restore only restarted the backend. `restore-archive.sh`
  now stops and (re)starts Caddy explicitly alongside the backend.

## [1.2.8] - 2026-07-20

### Fixed
- Restore from a backup archive always failed in the installed app with a false
  "no health.db" error. The restore script validated the archive with
  `tar -tzf | grep -qx "health.db"` under `set -o pipefail`; on the real
  (multi-100MB) backups tar took SIGPIPE on stdout once grep was done, and
  pipefail turned that into a spurious failure. The check now lists members to a
  temp file and greps that (no pipe), which is reliable for large archives.

## [1.2.7] - 2026-07-20

### Fixed
- Backup archives and the disaster-recovery restore trigger were written to a
  CWD-relative `data/` path, which under the systemd-hardened deployment is
  read-only (`/opt/health-manager/backend/data/`) and not where the restore unit
  looks — so on-server backups failed to write and "Restore" never triggered.
  `BACKUP_DIR` (and the restore request/result markers) now anchor to the live
  database directory (`/var/lib/health-manager/data/`), matching
  `restore-archive.sh` and the `health-manager-restore.path` unit.

### Changed
- Repository-wide formatting and professionalization: enforced `ruff format`
  across the backend, expanded the README, added `LICENSE` / `SECURITY` /
  `CONTRIBUTING` policies, OpenAPI metadata, hardened CI triggers and coverage
  gate, and reconciled environment configuration.

## [1.2.6] - 2026-07-20

### Added
- Document extraction now honors the household AI provider fallback sequence
  (previously hardcoded); reordering providers and the Cloud/Local primary
  toggle in Settings finally apply to extraction, not just chat/insights.
- Gemini authentication selector in Settings (Auto / ADC via Vertex AI / API
  Key), with the ADC option disabled when not configured server-side.
- Per-provider model selection is now honored by extraction (text and vision).
- Eye-icon detail flyout on each "Currently Taking" medicine row, surfacing the
  FDA label, frequently-reported adverse events, and patient-education links.
- Comprehensive Medication Report (card-level "Report" button) — a streamed AI
  overview of the whole regimen: medicines, drug interactions, schedule, and
  FDA safety alerts.

### Changed
- Extraction result cache key now embeds the provider plan, so reordering
  providers or changing a model invalidates stale cached results.
- Extraction prompt externalized to `prompts/extraction.md` for no-code tuning.
- Unconfigured-household extraction defaults to local (Ollama) first, matching
  chat/insights.

## [1.0.4] - 2026-06-18

### Added
- Doctor and lab summary views on member profiles.
- Configurable AI provider API keys (OpenAI, Gemini, Groq, OpenRouter).
- Drag-and-drop upload drop zone for health records.

### Fixed
- Debian package metadata parsing failure during install.
- Reorganized the source tree for clearer separation of concerns.

_Entries prior to 1.0.4 predate this changelog and are not reconstructed here._
