"""Extraction accuracy evaluation harness (Phase 4).

Measures how accurately the extraction pipeline turns document text into
structured ``ExtractedFields``. Synthetic golden documents carry ground truth;
``metrics`` scores field-level precision/recall/F1; ``evaluator`` runs the
real (or mocked) extractor and reports. Run the real baseline with:

    cd backend && uv run python -m tests.extraction.evaluator --real-ai
"""
