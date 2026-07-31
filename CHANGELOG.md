# Changelog

All notable changes to **Family Health Manager** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Document-processing speedup — Phase A–D.** Further pipeline improvements
  targeting the vision-fallback path (the slowest remaining route for multi-page
  scanned PDFs with poor OCR) and consistency fixes:
  - **Parallel vision batches (A1):** vision extraction batches now run
    concurrently on cloud (capped at `EXTRACTION_VISION_BATCH_CONCURRENCY`,
    default 4) instead of sequentially; local Ollama stays sequential (it
    serializes anyway). A 9-page scan with 3 batches runs ~3× faster on cloud.
  - **Transcription overlap (A2):** the vision transcription task is kicked off
    before the extraction batch loop and awaited after, overlapping the two
    (mirrors the OCR path's existing overlap). Saves one full vision round-trip.
  - **Parallel page rendering (A3):** pages for the vision fallback are rendered
    in parallel (bounded by `OCR_CONCURRENCY`) instead of sequentially.
  - **Bounded chunk concurrency for local (B1):** OCR chunk extraction is now
    capped at 2 concurrent calls on local Ollama (was unbounded, inflating RAM
    with zero throughput gain); cloud stays unbounded.
  - **OCR render reuse (B2):** page renders from the OCR pass are reused by the
    vision fallback (re-encoded to JPEG for ~5× smaller API payloads) instead of
    re-rendering the same pages — eliminates double rendering on every scanned
    PDF that escalates to vision. `extract_pdf_text` now returns
    `(text, page_count)` from a single `fitz.open`, removing the separate
    page-count validation open.
  - **Transcription through the provider chain (C1):** `_format_ocr_transcription`
    and `_transcribe_via_vision` now route through `_run_provider_chain` (respecting
    `EXTRACTION_RACE_PROVIDERS` and per-provider timeouts) instead of custom racing
    that fired every provider at once. The unused `_race_vision_entries` helper was
    removed.
  - **`call_ocr` timeout (C2):** OCR provider calls now respect
    `EXTRACTION_PROVIDER_TIMEOUT` / `EXTRACTION_LOCAL_TIMEOUT` — a dead Gemini key
    previously stalled indefinitely.
  - **Prompt hash in cache key (D2):** the extraction cache key now includes a
    hash of `prompts/extraction.md` content, so editing the prompt self-invalidates
    stale cached extractions without manually bumping `EXTRACTION_CACHE_VERSION`
    (bumped 4 → 5 to flush existing entries).
  - **Conditional image preprocessing (D3):** PIL preprocessing (contrast boost /
    threshold) is skipped for digitally-rendered PDF pages — it was designed for
    handwritten/faded photos and can degrade clean digital text. Uploaded images
    still get the full pipeline. Eval-gated: verify with the golden F1 harness.

## [1.3.0] - 2026-07-31

### Added
- **Native Save-As for PDF export.** Report PDFs (Smart Report, Health
  Assessment, pre-consultation) now open a native Save-As dialog in the desktop
  app and write the file to the chosen location (Tauri `dialog` + `fs` plugins);
  the browser/dev path falls back to a Downloads blob download.
- **Provenance + freshness on AI insights.** Member-level reports (Smart Report,
  Health Assessment, Medication) now ship a server-side source-record list +
  "Records as of {date}" line, rendered in a shared `ReportFooter`. Provenance is
  computed from real records — never from LLM output. New `ai_insights` columns
  `sources_json` / `freshness_as_of` / `range_start` (migration
  `p1q2r3s4t5u6_insight_provenance`).
- **Inline verification on Smart Report labs.** When the second-model check
  disputes a lab value/date, a ⚠ icon appears on that parameter row (correction
  in the tooltip) in addition to the global footnote.
- **Chronic conditions section** in the Smart Report, and per-section accent
  icons in the Health Assessment viewer.
- **Structured Medication Report.** The medication report is now typed JSON
  rendered as medicine cards, severity-colored interactions, schedule/adherence,
  safety alerts, and priority recommendations (markdown fallback on parse
  failure).

### Changed
- **Gemini-via-ADC, zero-config.** The backend auto-detects the standard gcloud
  credentials file (`~/.config/gcloud/application_default_credentials.json`) and
  infers the Vertex project from its `quota_project_id` — so the desktop app
  reaches Gemini via Vertex with no `.env`/`VERTEX_PROJECT` set.
- **Faster Gemini.** `GEMINI_SUPPRESS_THINK` (default on) sends
  `thinkingConfig.thinkingBudget=0`, roughly halving Gemini-2.5-flash latency
  (Smart Report ~27s → ~13s).
- **Thorougher Smart Report.** Comprehensive reports now analyze the full history
  (record cap 20 → 100) — every doctor visit, chronic condition, and lab.
- **Unified markdown rendering** across report viewers (single `MarkdownRenderer`;
  the hand-rolled `simpleMarkdown` was removed).
- **Desktop hardening.** Content Security Policy enabled (`script-src 'self'`,
  was `null`); the Save-As filesystem capability scoped to `$HOME/**` (was `**`).
- Pre-consultation notes remain markdown (the JSON attempt rendered as raw text).

### Fixed
- **PDF export broken in the desktop webview.** Tailwind v4's `oklch()` colors
  threw the old bundled `html2canvas`; switched to `html2canvas-pro` + `jspdf`.
- **ADC token refresh** serialized (double-checked lock) and warn-once on failure
  (was racing + log-spamming).
- `_pending_status` now handles naive/aware `generated_at` correctly.
- Tolerant JSON extraction now brace-balanced (was a greedy `\{.*\}` regex that
  could grab the wrong span).
- PDF export failure UX: the toast owns failures (no more double `window.print()`),
  and a Tauri write-failure is surfaced instead of silently dumping to Downloads.

## [1.2.10] - 2026-07-20

### Changed
- **Document-processing performance overhaul.** Extraction is LLM-bound (app-side
  overhead is ~0.1ms; the model call dominates by orders of magnitude), so the
  work targets call count, provider reliability, concurrency, and perceived
  latency rather than the Python pipeline:
  - **Provider-health negative cache (A1):** a TTL-cached pre-flight probe prunes
    confirmed-dead providers from the extraction chain before the sequential
    failover pays the 15s dead-key tax on each. `/ai/status` shares the probe, so
    opening the status panel warms it. No-op until a probe runs (existing
    sequential behaviour preserved).
  - **Opt-in provider racing (A2):** `EXTRACTION_RACE_PROVIDERS` (default off)
    races healthy cloud providers; local Ollama stays the sequential last resort.
  - **Fewer calls (A3/B2):** transcription-formatting now overlaps chunk
    extraction; multi-page scanned PDFs send `EXTRACTION_VISION_BATCH_SIZE` (3)
    page images per vision call (9 pages → 3 calls, was 9) with per-page fallback;
    `EXTRACTION_PAGES_PER_CHUNK` 3 → 5. Transcription is likewise batched.
  - **Local floor (B1/B3):** `OLLAMA_KEEP_ALIVE` 2m → 30m plus a background
    startup model warmup so the first extraction isn't cold; batch fan-out is
    provider-aware (local → 2, cloud → 8).
  - **Fast-model infra (B4, eval-gated):** `OLLAMA_FAST_MODEL` overrides the
    Ollama text-extraction entry only and is embedded in the cache fingerprint.
  - **Cloud-first auto (C1):** new `primary_provider="auto"` default prefers
    cloud when any key is configured, else local — a keyed household becomes
    30–60× faster with no Settings change; an Ollama-only box is unaffected.
  - **Cache (A5):** positive TTL 1d → 7d; no-data results are negative-cached
    briefly (only when no providers were pruned, so a fixed key isn't hidden).
  - **UX (D2/D4):** `/extract/stream` emits live per-stage progress
    (`{stage:"progress", pct, detail}`) plus a provider-health line ("no cloud
    keys — local CPU (slow)"); the upload UI surfaces it.
  - One structured per-extraction log line: `provider … cache=hit/miss elapsed_ms`.

### Fixed
- Extraction prompt content and `num_ctx` intentionally **unchanged** — they're
  load-bearing for the F1-0.99 accuracy baseline; trimming blind is deferred to
  the eval harness.

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
