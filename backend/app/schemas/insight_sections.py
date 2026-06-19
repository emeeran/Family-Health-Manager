"""Server-side parsing of the comprehensive AI insight into typed sections.

The insight prompt (``COMPREHENSIVE_INSIGHT_PROMPT``) emits exactly six
numbered markdown sections. Returning a structured ``sections`` array lets the
frontend style each section by a stable ``key`` instead of fuzzy-matching
titles, and removes the need for every client to re-implement the parser.
The frontend keeps its own ``parseSections`` as a fallback when ``sections``
is absent.
"""

from __future__ import annotations

import re

# A real section heading line, in any of the model's shapes:
#   "**1. Title**"  |  "1. **Title**"  |  "1. Title"  |  "### Title"
_HEADING_LINE = re.compile(r"^\s*(?:\*{0,2}\s*)?(?:#{1,3}\s+|\d+\.\s*)\S")
# Split point just before each heading (mirrors the TS parser's lookahead).
_SECTION_SPLIT = re.compile(r"(?=^(?:\s*\*{0,2}\s*\d+\.\s|#{1,3}\s))", re.MULTILINE)


def _clean_heading(line: str) -> str:
    """Strip leading/trailing markdown markers and a leading "N." from a heading."""
    s = re.sub(r"^[*\s#]+", "", line)
    s = re.sub(r"^\d+\.\s*", "", s)
    s = s.replace("*", "")
    s = re.sub(r"\s*[-:—]\s*$", "", s)
    return s.strip()


def _key_for(title: str) -> str:
    """Map a section title to a stable styling key."""
    t = title.lower()
    if "overview" in t:
        return "overview"
    if "active condition" in t or "conditions" in t:
        return "conditions"
    if "lab" in t:
        return "labs"
    if "risk" in t:
        return "risk"
    if "recommend" in t:
        return "recommendations"
    if "follow" in t:
        return "follow_up"
    return "other"


def parse_insight_sections(markdown: str) -> list[dict]:
    """Split a comprehensive insight into ``[{title, body, key}]``.

    Non-heading preamble (if the model adds one) is dropped. Returns ``[]``
    when the markdown has no recognizable sections.
    """
    if not markdown or not markdown.strip():
        return []

    sections: list[dict] = []
    for part in _SECTION_SPLIT.split(markdown):
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        first = lines[0].strip()
        if not _HEADING_LINE.match(first):
            # Stray preamble between headings — ignore.
            continue
        title = _clean_heading(first)
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        if not title:
            continue
        sections.append({"title": title, "body": body, "key": _key_for(title)})
    return sections
