"""Run extraction accuracy evaluation over the golden document set.

Mock mode (default, for CI/structure): injects the expected fields back through
the parser to verify the harness plumbing — scores will be perfect.

Real-AI mode: calls the actual LLM text-extraction path
(``call_text_extraction`` + ``parse_extraction``) on each golden doc and reports
field-level precision/recall/F1. This is the baseline / re-measurement tool.

    cd backend && uv run python -m tests.extraction.evaluator --real-ai
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import Awaitable, Callable

from app.schemas.health_record import ExtractedFields
from app.services.ai.document_extractor import parse_extraction

from .golden_documents import GOLDEN_DOCUMENTS
from .metrics import FieldScores, Score, score_extraction

# An extract_fn turns a golden doc's text into ExtractedFields.
ExtractFn = Callable[[str], Awaitable[ExtractedFields]]


async def evaluate(extract_fn: ExtractFn) -> list[tuple[str, FieldScores]]:
    rows: list[tuple[str, FieldScores]] = []
    for doc in GOLDEN_DOCUMENTS:
        extracted = await extract_fn(doc.text)
        rows.append((doc.name, score_extraction(extracted, doc.expected)))
    return rows


def _real_extract(text: str) -> "ExtractFn":
    async def fn(text: str) -> ExtractedFields:
        from app.services.ai.document_extractor import call_text_extraction

        ref = [""]
        raw = await call_text_extraction(text, ref)
        return parse_extraction(raw, ExtractedFields)

    return fn


def _print_report(rows: list[tuple[str, FieldScores]]) -> dict:
    print(f"\n{'document':<20} {'precision':>9} {'recall':>9} {'f1':>9}")
    print("-" * 50)
    overall = Score()
    per_field: dict[str, Score] = {}
    for name, fs in rows:
        agg = fs.aggregate()
        overall.tp += agg.tp
        overall.fp += agg.fp
        overall.fn += agg.fn
        for fname, s in fs.fields.items():
            slot = per_field.setdefault(fname, Score())
            slot.tp += s.tp
            slot.fp += s.fp
            slot.fn += s.fn
        print(f"{name:<20} {agg.precision:>9.2f} {agg.recall:>9.2f} {agg.f1:>9.2f}")
    print("-" * 50)
    print(f"{'OVERALL':<20} {overall.precision:>9.2f} {overall.recall:>9.2f} {overall.f1:>9.2f}")
    print("\nPer-field F1:")
    for fname, s in sorted(per_field.items()):
        if s.tp + s.fp + s.fn:
            print(f"  {fname:<22} P={s.precision:.2f} R={s.recall:.2f} F1={s.f1:.2f}")
    return {
        "overall": {"precision": overall.precision, "recall": overall.recall, "f1": overall.f1},
        "per_field": {k: asdict(v) for k, v in per_field.items()},
    }


async def _main(real_ai: bool, output: str | None) -> None:
    if real_ai:
        extract_fn = _real_extract("")
    else:
        async def mock_fn(text: str) -> ExtractedFields:
            # Round-trip the expected JSON through the parser to exercise the harness.
            for doc in GOLDEN_DOCUMENTS:
                if doc.text == text:
                    return parse_extraction(doc.expected.model_dump_json(), ExtractedFields)
            return ExtractedFields()

        extract_fn = mock_fn

    rows = await evaluate(extract_fn)
    report = _print_report(rows)
    if output:
        with open(output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraction accuracy evaluation")
    parser.add_argument("--real-ai", action="store_true", help="Call real LLM providers")
    parser.add_argument("--output", help="Write JSON report to this path")
    args = parser.parse_args()
    asyncio.run(_main(args.real_ai, args.output))


if __name__ == "__main__":
    main()
