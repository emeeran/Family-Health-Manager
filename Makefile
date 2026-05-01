# ─── SDD Pipeline Makefile ────────────────────────────────────────────────────
SHELL := /bin/bash
BACKEND := backend
PYTHON  := $(BACKEND)/.venv/bin/python
UV      := uv

.PHONY: help setup domain reqs spec review design code review-code test lint run clean

help:
	@echo ""
	@echo "  SDD Pipeline Commands"
	@echo "  ─────────────────────────────────────────"
	@echo "  make setup        Install / sync dependencies"
	@echo "  make domain       p0 · Domain analysis"
	@echo "  make reqs         p1 · Requirements"
	@echo "  make spec         p2 · Spec generation"
	@echo "  make review       p3 · Review gate (PASS required)"
	@echo "  make design       p4 · Architecture design"
	@echo "  make code         p5 · Code generation"
	@echo "  make review-code  p5.5 · Code bloat review"
	@echo "  make test         p6 · Run tests"
	@echo "  make lint         Ruff + mypy"
	@echo "  make run          Start dev server"
	@echo "  make clean        Remove __pycache__ and .pytest_cache"
	@echo ""

setup:
	cd $(BACKEND) && $(UV) sync

domain:
	@echo "── Phase 0: Domain Analysis ──"
	claude "Read raw_idea.txt and prompts/p0_domain.txt. Save outputs to docs/00-domain/DOMAIN.md and docs/00-domain/CONTEXT_MAP.md."

reqs: domain
	@echo "── Phase 1: Requirements ──"
	claude "Read docs/00-domain/DOMAIN.md and prompts/p1_requirements.txt. Save to docs/01-requirements/REQUIREMENTS.md."

spec: reqs
	@echo "── Phase 2: Spec Generation ──"
	claude "Read docs/01-requirements/REQUIREMENTS.md and prompts/p2_spec.txt. Save to docs/02-spec/SPEC.md."

review: spec
	@echo "── Phase 3: Review Gate ──"
	claude "Read docs/02-spec/SPEC.md and prompts/p3_review.txt. Save to docs/03-review/REVIEW.md. Print PASS or FAIL."
	@grep -q "^## Verdict: PASS" docs/03-review/REVIEW.md \
		|| (echo "❌ Review FAILED. Fix issues in REVIEW.md before proceeding." && exit 1)
	@echo "✔ Review PASSED. Proceeding..."

design: review
	@echo "── Phase 4: Design ──"
	claude "Read docs/02-spec/SPEC.md, docs/03-review/REVIEW.md, and prompts/p4_design.txt. Save to docs/04-design/DESIGN.md."

code: design
	@echo "── Phase 5: Implementation ──"
	claude "Read docs/02-spec/SPEC.md, docs/04-design/DESIGN.md, and prompts/p5_code.txt. Write code into backend/app/."

review-code: code
	@echo "── Phase 5.5: Code Review ──"
	claude "Read prompts/p5.5_review_code.txt and every file in backend/app/. Output the review to stdout."
	@echo ""
	@echo "If issues were found, fix them, then re-run: make review-code"

test: review-code
	@echo "── Phase 6: Tests ──"
	cd $(BACKEND) && $(UV) run pytest tests/ -v --tb=short

lint:
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run mypy app/

run:
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --reload --port 8000

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache"   -exec rm -rf {} + 2>/dev/null || true

all: domain reqs spec review design code review-code test
	@echo "✔ Full SDD pipeline complete."
