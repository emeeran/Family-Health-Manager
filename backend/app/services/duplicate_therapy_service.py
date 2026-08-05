"""Duplicate-therapy (same therapeutic class) detection.

Flags when a member is on two or more medications from the same therapeutic
class — a common real-world risk for multi-prescription patients (e.g. two
statins, two NSAIDs, an ACE inhibitor + an ARB). These are POTENTIAL duplicates
for clinician review, not certain errors: same-class pairing is occasionally
intentional (e.g. combination therapy, or a tolerated overlap during a switch).

Classification is keyword-based against a curated map of common high-risk
classes keyed by generic-name fragments. Brand names are resolved to generics
elsewhere (the medication ``medicine_key``); here we match on whichever of
``medicine`` / ``medicine_key`` carries a recognizable generic token.
"""

from __future__ import annotations

from dataclasses import dataclass

# Curated therapeutic classes → generic-name keyword fragments. Kept tight to
# the classes where unintended overlap is clinically meaningful (not every drug
# class). Lowercased substring match against the normalized generic name.
_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "statin": ("atorvastatin", "rosuvastatin", "simvastatin", "pravastatin",
               "fluvastatin", "lovastatin", "pitavastatin"),
    "NSAID": ("ibuprofen", "diclofenac", "naproxen", "ketorolac", "aceclofenac",
              "etodolac", "meloxicam", "piroxicam", "indomethacin", "ketoprofen",
              "dexketoprofen", "nabumetone", "etoricoxib", "celecoxib", "mefenamic"),
    "ACE inhibitor": ("enalapril", "lisinopril", "ramipril", "perindopril",
                      "captopril", "trandolapril", "fosinopril"),
    "ARB": ("losartan", "telmisartan", "valsartan", "olmesartan", "irbesartan",
            "candesartan", "azilsartan"),
    "beta-blocker": ("metoprolol", "atenolol", "bisoprolol", "carvedilol",
                     "propranolol", "nebivolol", "sotalol", "labetalol"),
    "calcium-channel blocker": ("amlodipine", "nifedipine", "diltiazem",
                                 "verapamil", "cilnidipine", "lercanidipine", "felodipine"),
    "thiazide-like diuretic": ("hydrochlorothiazide", "chlorthalidone",
                               "indapamide", "metolazone"),
    "loop diuretic": ("furosemide", "torsemide", "bumetanide"),
    "PPI": ("omeprazole", "pantoprazole", "rabeprazole", "esomeprazole",
            "lansoprazole", "dexlansoprazole", "ilaprazole"),
    "sulfonylurea": ("glimepiride", "gliclazide", "glipizide", "glibenclamide",
                     "glyburide"),
    "SGLT2 inhibitor": ("empagliflozin", "dapagliflozin", "canagliflozin",
                        "ertugliflozin"),
    "DPP-4 inhibitor": ("sitagliptin", "vildagliptin", "linagliptin",
                        "saxagliptin", "teneligliptin"),
    "SSRI": ("sertraline", "fluoxetine", "escitalopram", "citalopram",
             "paroxetine", "fluvoxamine"),
    "benzodiazepine": ("alprazolam", "clonazepam", "diazepam", "lorazepam",
                       "chlordiazepoxide", "nitrazepam", "midazolam"),
}


@dataclass(frozen=True)
class DuplicateTherapyFinding:
    """A potential same-class duplicate-therapy flag for clinician review."""

    therapeutic_class: str
    medications: list[str]  # display names of the overlapping meds

    def to_dict(self) -> dict:
        return {
            "therapeutic_class": self.therapeutic_class,
            "medications": self.medications,
        }


def classify_medication(name: str) -> str | None:
    """Return the therapeutic class for *name*, or ``None`` if unclassified.

    Matches on a lowercased substring of the generic/brand name against the
    curated keyword map.
    """
    if not name:
        return None
    hay = name.lower()
    for cls, keywords in _CLASS_KEYWORDS.items():
        if any(kw in hay for kw in keywords):
            return cls
    return None


def detect_duplicate_therapy(medications: list) -> list[DuplicateTherapyFinding]:
    """Flag classes where ≥2 distinct active medications overlap.

    *medications* is a list of medication dicts (as returned by
    ``MemberService.get_active_medications``) or Medication ORM objects — either
    is accepted. Inactive meds are ignored. Exact-duplicate entries (same
    ``medicine_key``) within a class collapse to a single med so a refill doesn't
    look like duplicate therapy.
    """
    def _get(med, name, default=""):
        if isinstance(med, dict):
            return med.get(name, default)
        return getattr(med, name, default)

    # class -> {medicine_key: display_name}
    by_class: dict[str, dict[str, str]] = {}
    for med in medications:
        if _get(med, "status", "active") != "active":
            continue
        # Prefer the normalized key for dedup; classify on whichever carries a
        # recognizable generic token.
        key = _get(med, "medicine_key") or _get(med, "medicine")
        display = _get(med, "medicine") or key
        cls = classify_medication(display) or classify_medication(key)
        if not cls:
            continue
        by_class.setdefault(cls, {})[str(key)] = display

    findings: list[DuplicateTherapyFinding] = []
    for cls, meds in by_class.items():
        if len(meds) >= 2:
            findings.append(
                DuplicateTherapyFinding(
                    therapeutic_class=cls,
                    medications=sorted(meds.values()),
                )
            )
    findings.sort(key=lambda f: f.therapeutic_class)
    return findings
