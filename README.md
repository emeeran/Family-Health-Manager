# hdd-health-manager

> Generated with the SDD Bootstrap script.

## Quick Start

```bash
make setup        # Install dependencies
# Edit raw_idea.txt, then:
make all          # Run the full SDD pipeline
```

## SDD Pipeline

| Phase | Command        | Output                              |
|-------|----------------|-------------------------------------|
| 0     | `make domain`  | `docs/00-domain/DOMAIN.md`          |
| 1     | `make reqs`    | `docs/01-requirements/REQUIREMENTS.md` |
| 2     | `make spec`    | `docs/02-spec/SPEC.md`              |
| 3     | `make review`  | `docs/03-review/REVIEW.md` (gate)   |
| 4     | `make design`  | `docs/04-design/DESIGN.md`          |
| 5     | `make code`    | `backend/app/`                      |
| 5.5   | `make review-code` | Bloat report (auto-fix)          |
| 6     | `make test`    | Test results + coverage             |

See [CLAUDE.md](CLAUDE.md) for full context.
