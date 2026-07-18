# Blind Review — verbatim from a sanitized, context-blind subagent

> This review was produced by a fresh subagent that received **no mention of the
> cleanup pipeline, its phases, `trash2review`, `AUDIT.md`, or that any refactor
> happened.** It was framed as an ordinary cold due-diligence review. The output
> below is saved verbatim, unedited by the main thread.

---

You're doing due diligence on a codebase before your team takes over on-call for it. Review it as a senior engineer seeing it for the first time.

The codebase is at /home/em/code/finished/health-manager — a self-hosted family health-record manager (FastAPI + React, SQLite/PostgreSQL, AI-powered document extraction). Backend in backend/app, frontend in frontend/src.

## P0 — Will page you, or put users at risk

1. **Drug-interaction failures return empty `[]`, indistinguishable from "no interactions."** Every external DDI / recall / label path catches `Exception`, logs, returns `[]`. The router surfaces `{"interactions": []}`. A false negative a layperson will trust.
2. **Background tasks fire before the request session commits** — the team's own documented landmine (`MEMORY.md`), still live at `health_records.py:764-778`.
3. **Encryption key is not part of the backup archive** — restore onto fresh hardware produces undecryptable data. Backup is theatre without the key.
4. **Router-level drug endpoints and the entire auth lifecycle are untested.** Zero router tests for member_drug_info / member_drug_interactions; zero tests for 2FA, refresh-token rotation, revocation.
5. **Frontend version (1.0.4) and backend version (1.1.1) have drifted, with no skew check.**

## P1 — Real bugs, slower to bite

6. **`/health` returns 200 without checking the DB or external deps.**
7. **Rate limiter is scaffolding — wired but never applied to any router.** Brute-force protection on 2FA is weaker than it looks.
8. **2FA bypass via password reset** — sessions revoke but 2FA state isn't re-verified.
9. **Single Fernet master key, hardcoded static salt, no rotation.**
10. **Silent failure cascade in scheduled jobs.** `jobs.py` (728 LOC, **zero tests**). Backup rotation fails → disk fills; reminders silently stop.
11. **`household.py` reset endpoint runs raw f-string SQL** over table names. Hardcoded today but one refactor from injection.

## P2 — Inconsistency / smells

12. **30 routers with no shared shape** — only ~15% use `response_model=`.
13. **Service layer split personality** — flat files next to provider subdirs next to a 1.3k-line facade.
14. **Status-code lottery** for similar errors (404/422/400/502 inconsistently).
15. **Over-engineering** — Redis, APScheduler, 9 jobs for a single-family app. Most is unused scaffolding.
16. **Frontend has zero component/page/E2E tests** — 9 tests, all on `lib/` pure functions.
17. **AI-extraction JSON parse failures return `[]` silently** — same pattern as #1 in a different subsystem.

## What's genuinely solid

- Argon2 password hashing; refresh-token rotation with replay detection; household-scoped auth; magic-byte file validation; request-ID middleware; CI with ruff+mypy+pytest+pip-audit.
- The MEMORY.md operational documentation is unusually good.

## Top 3 before taking the pager

1. Make DDI endpoints return an explicit `status: "error" | "ok"` field; add router tests.
2. Add `await db.commit()` between `create_record()` and `background_tasks.add_task` (one-line fix).
3. Include encryption key material in backup archive; make `/health` check the DB.

---

## Honest limit

This subagent runs on the same underlying model as the pipeline. A sanitized,
context-blind pass removes *self-grading bias* and *framing bias*, which are real
and fixable. It does **not** remove blind spots the model itself has regardless of
context. For a genuinely independent signal, paste a sample of the finished code
into a **brand-new session** with no relation to this one and ask the same cold-review
question.
