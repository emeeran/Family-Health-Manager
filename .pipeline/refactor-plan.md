# Phase 2 — Debloat & Refactor Plan (DRY RUN)

Scan date: 2026-07-18. Per-module, behavior-preserving only.

## What I looked for
Single-impl abstractions, defensive over-validation, dead branches/flags,
repeated logic, over-broad `except`, comment noise, dead config.

## Findings — the repo is already lean
The mature, pre-existing code shows no high-value safe targets (no single-impl
factories, no obvious dead branches). Aggressive refactoring of hand-written
human code would risk behavior changes and violate "boring over clever / match
existing conventions" — so this phase targets only **verified dead code**, all
zero-behavior-change:

| Unit | Change | Why safe | Lines |
|------|--------|----------|-------|
| `backend/app/services/drug_info/base.py` | **Delete `gather_results()`** | 0 callers (I wrote it, never used it — service uses inline loops). | ~20 |
| `backend/app/services/drug_info/base.py` | **Drop `not_found_is_empty` param + docstring line from `fetch_json`** | Never passed by any of its 12 callers; never referenced in the function body. | ~3 |
| `backend/app/core/config.py` | **Delete `SMTP_HOST/PORT/USER/PASSWORD/FROM` + `EMAIL_ENABLED`** | Only consumer (`email_service.py`) moved to trash2review in Phase 1. No remaining readers. | 6 |

## Evaluated and KEPT (flagged for AUDIT.md, not changed here)
- **12 broad `except Exception` in `drug_info`/`health_resources` providers.**
  These wrap external HTTP lookups and intentionally degrade to empty so a
  patient-facing panel never 500s on a bad upstream response. Each logs with
  `exc_info=True`, so real bugs surface in logs rather than being silently
  swallowed. Narrowing to `(httpx.HTTPError, ValueError)` would make panels
  *more* fragile (500 on an unexpected `KeyError`/`TypeError` from a malformed
  response) — a behavior change, so left as-is per the pipeline's "don't change
  observable behavior" rule. Noted as accepted-risk in `AUDIT.md`.

## Out of scope (would change behavior or risk regressions)
- Any rename/restructure of pre-existing modules.
- Deduping the parallel `drug_info` / `health_resources` shapes (intentional
  consistent pattern, not harmful duplication).
