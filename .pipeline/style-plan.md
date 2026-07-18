# Phase 3 — Style & Authorship Pass (applied)

Date: 2026-07-18.

## Applied
- **One formatting standard:** ran `ruff format` across the backend — **29
  files** conformed to the project's *already-configured* ruff format spec
  (194 were already formatted; the 29 were outliers including recent test
  files and a few older ones). Frontend was already **100% prettier-clean**
  (lefthook enforces it on every commit). No new style imposed — this brought
  outliers in line with the dominant existing convention.
- **AI-voice scan:** no emoji, exclamation-heavy phrasing, or debug `print()`/
  `console.log` in backend `app/` or frontend `src/`. (The single `print(`
  match is a legitimate secret-generation instruction inside an error string
  in `config.py`.) No action needed.
- **Naming:** no `Manager`/`Handler`/`Helper`/`Util` class suffixes found. The
  `*Service` suffix (`MemberService`, `DrugInfoService`, `HealthResourcesService`,
  `AIService`) is the codebase's established convention — kept.

## Deferred (large / risky — flagged for human decision, not changed)
- **Repo-wide error-handling philosophy unification.** The codebase mixes
  styles (raise in some routers, sentinel/None returns in the drug-info &
  health-resources providers, try/except-and-degrade in external-API code).
  The degrade-to-empty pattern in the new external-API providers is deliberate
  and consistent *within that layer* (patient-facing panels must never 500 on
  upstream failure). Forcing the rest of the codebase onto one philosophy
  would be a large, behavior-changing refactor — out of scope for a cleanup
  that must not change observable behavior.
- **Docstring format unification (Google/reST/NumPy).** The repo uses a mix;
  normalizing repo-wide is high-churn/low-value. Deferred.
- **Enforce `ruff format` in lefthook pre-commit** (currently only
  `ruff check --fix` runs, which is why the 29 files drifted). Recommended
  follow-up so formatting can't regress — left to the human since `lefthook.yml`
  was just edited.

## Verification
476 tests collect; `app.main` imports; ruff format now reports 223/223 clean.
