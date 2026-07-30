"""Regression tests for the insight prompt templates."""

from app.prompts.insight_prompts import PRE_CONSULT_PROMPT


def test_preconsult_prompt_formats_without_error() -> None:
    """PRE_CONSULT_PROMPT is ``.format()``-ed at runtime (specialty/symptoms
    placeholders). It must not contain stray literal ``{``/``}`` that would make
    ``.format()`` raise ``KeyError`` (a prior JSON-schema version crashed
    pre-consultation generation this way).
    """
    out = PRE_CONSULT_PROMPT.format(
        specialty_section="\nCTX", symptoms_section="\nSYM", specialty_focus="\nFOCUS"
    )
    # Placeholders filled, not left as literal {specialty_section}.
    assert "{specialty" not in out
    assert "CTX" in out and "SYM" in out and "FOCUS" in out
    # Markdown section headings present.
    assert "Hx (MEDICAL HISTORY)" in out
    # No leftover braces (the only braces were the three placeholders).
    assert out.count("{") == 0 and out.count("}") == 0
