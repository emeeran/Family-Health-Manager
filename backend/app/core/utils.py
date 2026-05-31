"""Shared utility functions."""
from __future__ import annotations

from datetime import date


def calculate_age(dob: date, reference: date | None = None) -> int:
    """Calculate age from date of birth."""
    today = reference or date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )
