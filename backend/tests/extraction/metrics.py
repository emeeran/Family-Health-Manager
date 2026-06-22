"""Field-level scoring for extraction accuracy.

Convention (per scalar field):
  - both absent              -> ignored (not applicable)
  - both present, equal      -> 1 true positive (TP)
  - expected present, miss   -> 1 false negative (FN)
  - extracted spurious       -> 1 false positive (FP)
  - both present, differ     -> 1 FN (the correct value was not retrieved)

Arrays (prescriptions / lab_tests) are matched element-by-element on a key
(medicine / test_name); unmatched expected rows are FN, unmatched extracted
rows are FP.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date

from app.schemas.health_record import ExtractedFields

SCALAR_FIELDS = (
    "record_type",
    "record_date",
    "record_time",
    "diagnosis",
    "existing_conditions",
    "chief_complaint",
    "investigations",
    "provider_name",
    "prescription_text",
    "next_review_date",
    "weight",
    "height",
    "blood_pressure",
    "heart_rate",
    "temperature",
)

ARRAY_FIELDS = {"prescriptions": "medicine", "lab_tests": "test_name"}


def _norm(v: object) -> str | None:
    """Normalize a value for comparison: enums→value, dates→ISO, lowercase trim."""
    if v is None:
        return None
    if isinstance(v, enum.Enum):
        v = v.value
    if isinstance(v, date):
        v = v.isoformat()
    s = str(v).strip().lower()
    return s or None


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class FieldScores:
    fields: dict[str, Score] = field(default_factory=dict)

    def aggregate(self) -> Score:
        tot = Score()
        for s in self.fields.values():
            tot.tp += s.tp
            tot.fp += s.fp
            tot.fn += s.fn
        return tot


def _score_scalar(extracted: ExtractedFields, expected: ExtractedFields, name: str) -> Score:
    e = _norm(getattr(expected, name, None))
    x = _norm(getattr(extracted, name, None))
    if e is None and x is None:
        return Score()  # not applicable
    if e is not None and x is not None:
        return Score(tp=1) if e == x else Score(fn=1)
    if e is not None:
        return Score(fn=1)
    return Score(fp=1)


def _score_array(
    extracted: ExtractedFields, expected: ExtractedFields, name: str, key: str
) -> Score:
    exp_rows = getattr(expected, name, None) or []
    ext_rows = list(getattr(extracted, name, None) or [])
    tp = fp = fn = 0
    for exp_row in exp_rows:
        exp_key = _norm(exp_row.get(key)) if isinstance(exp_row, dict) else None
        match_idx = None
        if exp_key:
            for i, cand in enumerate(ext_rows):
                cand_key = _norm(cand.get(key)) if isinstance(cand, dict) else None
                if cand_key == exp_key:
                    match_idx = i
                    break
        if match_idx is not None:
            tp += 1
            ext_rows.pop(match_idx)
        else:
            fn += 1
    fp += len(ext_rows)
    return Score(tp=tp, fp=fp, fn=fn)


def _score_eyeglass(extracted: ExtractedFields, expected: ExtractedFields) -> Score:
    exp = expected.eyeglass or {}
    ext = extracted.eyeglass or {}
    if not exp and not ext:
        return Score()
    keys = set(exp) | set(ext)
    tp = fn = 0
    for k in keys:
        if _norm(exp.get(k)) == _norm(ext.get(k)) and _norm(exp.get(k)) is not None:
            tp += 1
        elif _norm(exp.get(k)) is not None:
            fn += 1
    fp = sum(1 for k in keys if _norm(exp.get(k)) is None and _norm(ext.get(k)) is not None)
    return Score(tp=tp, fp=fp, fn=fn)


def score_extraction(extracted: ExtractedFields, expected: ExtractedFields) -> FieldScores:
    """Score an extraction against ground truth, field by field."""
    scores = FieldScores()
    for name in SCALAR_FIELDS:
        scores.fields[name] = _score_scalar(extracted, expected, name)
    for name, key in ARRAY_FIELDS.items():
        scores.fields[name] = _score_array(extracted, expected, name, key)
    scores.fields["eyeglass"] = _score_eyeglass(extracted, expected)
    return scores
