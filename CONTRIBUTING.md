# Contributing to Family Health Manager

Thanks for your interest in improving Family Health Manager! This guide covers
the contribution workflow. See [`CLAUDE.md`](CLAUDE.md) for deeper engineering
context and conventions.

## Development Setup

```bash
git clone <repo-url> health-manager && cd health-manager
cp backend/.env.example backend/.env   # then fill in SECRET_KEY
./dev.sh                                 # backend (:8000) + frontend (:3000)
```

The Vite dev proxy forwards `/api` to the backend, so no CORS configuration is
needed in development.

## Branching & Commits

- Branch from `develop` using a conventional prefix: `feature/`, `fix/`,
  `chore/`, or `docs/`.
- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Never commit directly to `main`.
- Never commit `backend/.env` or any other file containing secrets.

## Checks Before Pushing

```bash
# Backend
cd backend && uv run ruff check --fix . && uv run mypy app/ && uv run pytest

# Frontend
cd frontend && npm run lint && npx tsc --noEmit && npm test
```

These also run automatically via [lefthook](lefthook.yml) (pre-commit: ruff +
prettier; pre-push: mypy + tsc) and in [CI](.github/workflows/ci.yml).

## Spec-Driven Development

Substantial features follow the SDD pipeline driven by the `Makefile`:

```
make domain → make reqs → make spec → make review → make design → make code → make test
```

Artefacts land in [`docs/`](docs/). Start there for any non-trivial change so the
specification stays in sync with the implementation.

## Reporting Issues

Open a GitHub issue with a clear title, steps to reproduce, expected vs. actual
behaviour, and your environment (OS, browser, deployment method). For security
issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
