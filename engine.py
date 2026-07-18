from __future__ import annotations
import re
from typing import List, Optional, Set
from defined_terms import is_defined_term
from detectors import Detector, Match
from substitution import Substitutor

# When two detectors claim overlapping spans, structured regex types win
# over NER types (they're near-deterministic on well-formed input), and
# within a tier, the longer span wins (e.g. a full phone number over a
# partial digit run).
PRIORITY = {
    "EMAIL_ADDRESS": 0,
    "PHONE_NUMBER": 1,
    "SSN": 0,
    "CREDIT_CARD_NUMBER": 0,
    "IP_ADDRESS": 0,
    "DATE_OF_BIRTH": 0,
    "ADDRESS": 1,        # whole-paragraph address blocks should win over
                          # a COMPANY_NAME/FULL_NAME fragment spaCy found
                          # inside the same address (e.g. a building name)
    "COMPANY_NAME": 2,
    "FULL_NAME": 2,
}

_NER_LABELS = {"COMPANY_NAME", "FULL_NAME", "ADDRESS"}
_HAS_ALPHA_RE = re.compile(r"[A-Za-z]")
_FISCAL_YEAR_RE = re.compile(r"^fiscals?\s*\d{4}$", re.IGNORECASE)


def _resolve_overlaps(matches: List[Match]) -> List[Match]:
    """Greedy interval selection: sort by (priority tier, -length), keep a
    match only if it doesn't overlap something already kept."""
    ordered = sorted(
        matches,
        key=lambda m: (PRIORITY.get(m.label, 9), -(m.end - m.start), m.start),
    )
    kept: List[Match] = []
    occupied: List[tuple] = []

    def overlaps(a, b):
        return not (a[1] <= b[0] or b[1] <= a[0])

    for m in ordered:
        span = (m.start, m.end)
        if any(overlaps(span, o) for o in occupied):
            continue
        kept.append(m)
        occupied.append(span)

    return sorted(kept, key=lambda m: m.start)


class RedactionEngine:
    def __init__(
        self,
        detectors: List[Detector],
        substitutor: Substitutor,
        defined_terms: Optional[Set[str]] = None,
    ):
        self.detectors = detectors
        self.substitutor = substitutor
        self.defined_terms = defined_terms or set()

    def _passes_precision_filters(self, m: Match) -> bool:
        if m.label not in _NER_LABELS:
            return True
        if not _HAS_ALPHA_RE.search(m.text):
            return False  # e.g. a bare currency symbol mis-tagged as ORG
        if _FISCAL_YEAR_RE.match(m.text.strip()):
            return False  # e.g. "Fiscal 2025" / "Fiscals 2024" mis-tagged as LOCATION
        if is_defined_term(m.text, self.defined_terms):
            return False  # e.g. "the Promoter Selling Shareholders"
        return True

    def find_matches(self, text: str) -> List[Match]:
        raw: List[Match] = []
        for d in self.detectors:
            raw.extend(d.detect(text))
        raw = [m for m in raw if self._passes_precision_filters(m)]
        return _resolve_overlaps(raw)

    def redact(self, text: str) -> tuple[str, List[dict]]:
        matches = self.find_matches(text)
        if not matches:
            return text, []

        out_parts = []
        audit = []
        cursor = 0
        for m in matches:
            out_parts.append(text[cursor:m.start])
            replacement = self.substitutor.substitute(m.text, m.label)
            out_parts.append(replacement)
            audit.append({
                "original": m.text,
                "type": m.label,
                "replacement": replacement,
                "start": m.start,
                "end": m.end,
            })
            cursor = m.end
        out_parts.append(text[cursor:])
        return "".join(out_parts), audit
