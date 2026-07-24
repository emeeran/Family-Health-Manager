"""Drug composition parsing + name normalization for the drug-info pipeline.

Shared by the local-catalog seed script/provider
(:mod:`app.services.drug_info.providers.local_catalog`) and the brand→generic
heuristic in :mod:`app.services.drug_info.service`.
"""

from __future__ import annotations

import re

# Dosage tokens to drop when normalizing a name ("500mg", "0.5 mcg", "10 units").
_DOSAGE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|ug|ml|gm|g|iu|meq|%|units?)\b", re.I)

# Form words / modifier suffixes common in South-Asian brand names
# ("Tab/Cap/Syp/Inj/…", "Tablet PR/SR/ER"). Dropped during normalization.
_FORM_WORDS = {
    "tab",
    "tabs",
    "tablet",
    "tablets",
    "cap",
    "caps",
    "capsule",
    "capsules",
    "syp",
    "syrup",
    "inj",
    "injection",
    "drops",
    "drop",
    "cream",
    "ointment",
    "gel",
    "inhaler",
    "puff",
    "spray",
    "suspension",
    "susp",
    "strip",
    "sachet",
    "pr",
    "sr",
    "er",
    "xr",
    "ds",
    "hs",
}

# One ingredient entry: a name + an optional parenthesized strength.
_INGREDIENT_RE = re.compile(r"^\s*([A-Za-z][A-Za-z\- ']*)\s*(?:\(([^)]*)\))?\s*$")


def parse_composition(composition: str) -> list[dict]:
    """Parse a composition string into ``[{"name", "strength"}]``.

    Handles ``"Metformin (500mg)"`` and combinations joined by ``+`` / ``,``:
    ``"Glimepiride (0.5mg) + Metformin (500mg)"``. ``strength`` is ``None`` when
    absent. Returns ``[]`` for empty/unparseable input.
    """
    if not composition or not composition.strip():
        return []
    out: list[dict] = []
    for part in re.split(r"\s*[+,]\s*", composition):
        part = part.strip()
        if not part:
            continue
        m = _INGREDIENT_RE.match(part)
        if not m:
            continue
        name = m.group(1).strip()
        strength = (m.group(2) or "").strip() or None
        if name:
            out.append({"name": name, "strength": strength})
    return out


def ingredient_names(composition: str) -> list[str]:
    """Lowercased distinct ingredient names from a composition string."""
    seen: list[str] = []
    for ing in parse_composition(composition):
        n = ing["name"].lower()
        if n and n not in seen:
            seen.append(n)
    return seen


def normalize_drug_name(name: str) -> str:
    """Normalize a brand/generic name for matching.

    Lowercases, strips parentheticals, dosage tokens, bare numbers, punctuation,
    and form words; collapses whitespace. e.g. ``"Glycomet-GP 0.5 Tablet PR"``
    → ``"glycomet gp"``. Returns ``""`` for empty input.
    """
    if not name:
        return ""
    s = re.sub(r"\([^)]*\)", " ", name.lower())
    s = _DOSAGE_RE.sub(" ", s)  # "0.5mg", "500 mg"
    s = re.sub(r"\b\d+(?:\.\d+)?\b", " ", s)  # bare numbers: "0.5", "500"
    s = re.sub(r"[^a-z0-9\s]", " ", s)  # punctuation → space (hyphens split)
    words = [w for w in s.split() if w and w not in _FORM_WORDS]
    return " ".join(words).strip()
