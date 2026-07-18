# Phase 1 — Redundant File Purge Plan (DRY RUN)

Scan date: 2026-07-18. Branch: `cleanup/pipeline-2026-07-18`.

## Headline
The repo is already clean on the high-confidence axes:
- **No committed build/cache artifacts** (`__pycache__`, `*.pyc`, `node_modules`, `dist/`, `*.map`, `.DS_Store`) — already gitignored correctly. Nothing to `.gitignore`-remove.
- **No exact-duplicate files** (content-hash across all 545 source files: zero dupes).
- **No dead-tell filenames** (`_old`, `_v2`, `_copy`, `_backup`, `.bak`, `~`, `deprecated`) — one false-positive (`test_backup_restore.py`, a live test).
- **No superseded v1-beside-v2 generations.**

## Candidates (by confidence)

| Path | Reason | Confidence | Inbound refs (app) | In tests? |
|------|--------|-----------|--------------------|-----------|
| `backend/app/services/email_service.py` | Dead code: zero importers anywhere; only a related `EMAIL_ENABLED` knob in config. Email feature was written but never wired in. | **High** | 0 | 0 |
| `backend/app/core/migrate_files.py` | Documented "one-time storage migration script"; now zero importers. Ambiguous: intentional migration-history (keep) vs. spent script (move). | Low (ambiguous) | 0 | 0 |
| `backend/scripts/export_openapi.py` | Standalone utility script; no Makefile/CI/script refs. Ambiguous: manual dev tool (keep) vs. unused (move). | Low (ambiguous) | 0 (not imported — scripts are invoked, not imported) | n/a |

## Recommendation
- **Move (high confidence):** `backend/app/services/email_service.py` → `trash2review/backend/app/services/email_service.py`.
- **Move (ambiguous — pipeline default is to move, reversible):** `backend/app/core/migrate_files.py` and `backend/scripts/export_openapi.py`. **Flag for your veto** during review — restore either with `git mv trash2review/<path> <path>` if it's still load-bearing.

## Deferred to Phase 2 (debloat), not Phase 1
- `EMAIL_ENABLED` + SMTP_* settings in `backend/app/core/config.py` (dead config if email_service.py is removed). Will be removed in the Phase 2 config-knob pass.

## Out of scope
- Frontend components spot-checked (recent ones — `clinical-trials-card`, `canadian-din-lookup`, `drug-interaction-report` — are all wired in via the tabs). No frontend orphans found in the sample.
- `trash2review/` existing contents (313 MB, gitignored) are already parked — out of scope.

## Verification after apply
- Re-run `uv run pytest` + `vitest run`; if anything breaks, `git mv` the file back (it was a false positive — most likely `export_openapi.py` if some tool invokes it).
