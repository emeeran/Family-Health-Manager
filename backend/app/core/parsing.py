"""Shared parsing utilities."""
import re


def parse_duration(duration_str: str | None) -> int:
    """Parse a human-readable duration into days.

    Supported patterns:
      - "30 days", "30 day"
      - "2 weeks", "2 week"
      - "1 month", "3 months"
      - Bare number (treated as days)

    Returns 30 if the string cannot be parsed.
    """
    if not duration_str:
        return 30

    text = str(duration_str).strip().lower()

    m = re.match(r"([0-9]+)\s*days?", text)
    if m:
        return int(m.group(1))

    m = re.match(r"([0-9]+)\s*weeks?", text)
    if m:
        return int(m.group(1)) * 7

    m = re.match(r"([0-9]+)\s*months?", text)
    if m:
        return int(m.group(1)) * 30

    m = re.match(r"([0-9]+)$", text)
    if m:
        return int(m.group(1))

    return 30
