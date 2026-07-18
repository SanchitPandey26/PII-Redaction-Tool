from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Callable, List, Optional
import spacy

@dataclass
class Match:
    start: int
    end: int
    text: str
    label: str        # e.g. "EMAIL_ADDRESS", "FULL_NAME", "PHONE_NUMBER"
    source: str        # which detector produced it (for auditing / debugging)


class Detector:
    label: str = "UNKNOWN"

    def detect(self, text: str) -> List[Match]:
        raise NotImplementedError

class RegexDetector(Detector):
    """Generic regex detector. `group` lets a detector match on a captured
    sub-span rather than the whole regex match (used by DOB, which needs a
    context keyword like 'Date of Birth:' to avoid flagging every date in a
    500-page legal filing, but should only redact the date value itself)."""

    def __init__(
        self,
        label: str,
        pattern: str,
        flags: int = 0,
        group: int = 0,
        validator: Optional[Callable[[str], bool]] = None,
    ):
        self.label = label
        self.pattern = re.compile(pattern, flags)
        self.group = group
        self.validator = validator

    def detect(self, text: str) -> List[Match]:
        out = []
        for m in self.pattern.finditer(text):
            if m.group(self.group) is None:
                continue
            start, end = m.span(self.group)
            value = text[start:end]
            if self.validator and not self.validator(value):
                continue
            out.append(Match(start, end, value, self.label, self.__class__.__name__))
        return out


def _luhn_valid(number: str) -> bool:
    """Luhn checksum -- filters out 13-19 digit runs that aren't real card
    numbers (e.g. long registration/reference numbers in legal documents)."""
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


_YEAR_RANGE_RE = re.compile(r"^(19|20)\d{2}[\s\-](19|20)\d{2}$")


def _phone_context_ok(value: str) -> bool:
    """Cheap sanity filter: reject obvious non-phone numeric runs -- fiscal
    year ranges ('2022-2023'), and anything with too few/many digits to be
    a real phone number."""
    if _YEAR_RANGE_RE.match(value.strip()):
        return False
    digits = re.sub(r"\D", "", value)
    return 7 <= len(digits) <= 13


EMAIL_DETECTOR = RegexDetector(
    label="EMAIL_ADDRESS",
    pattern=r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
)

# Indian + generic phone numbers. Source formatting in this document is
# inconsistent -- "+91 9876543210", "+ 91 20 4505 3237" (space after the
# plus), and "+ 91 20 45053237" (no internal spacing) all appear -- so the
# prefix allows an optional space after '+' and the body allows 2-4
# digit groups to cover 10-digit numbers written as one block or split
# by area code / exchange / line the way Indian landlines commonly are.
_PHONE_PATTERN = re.compile(
    r"(?<![\w/.\-])(?:\+\s?91[\s\-]?)?(?:\(?0\d{2,4}\)?[\s\-]?)?"
    r"\d{2,5}[\s\-]?\d{2,5}[\s\-]?\d{0,5}[\s\-]?\d{0,5}(?![\w])"
)
_PHONE_CONTEXT_RE = re.compile(r"(tel(ephone)?|phone|mobile|contact|fax|\bph\b)\s*[:.]?\s*$", re.IGNORECASE)


class PhoneDetector(Detector):
    """A bare 8-10 digit run is ambiguous in a legal/financial document --
    it could be a phone number, but could just as easily be a reference
    number, application number, or registration ID (this document has
    plenty, e.g. 'reference number 20220803-40'). To keep precision
    reasonable we only accept a bare digit run as PHONE if it's preceded
    by '+91'/'0<area code>' or a nearby context keyword like 'Telephone:'.
    """

    label = "PHONE_NUMBER"

    def detect(self, text: str) -> List[Match]:
        out = []
        for m in _PHONE_PATTERN.finditer(text):
            value = m.group(0)
            if not _phone_context_ok(value):
                continue
            # STD/area-code branch requires an actual separator after the
            # code (e.g. "022-..." or "020 ...") -- a bare contiguous
            # digit run that merely happens to start with '0' (an
            # application/reference number, not a phone number) must not
            # qualify here.
            has_country_or_area_code = bool(re.match(r"\s*(\+\s?91|\(?0\d{1,4}[\s\-)])", value))
            if not has_country_or_area_code:
                window = text[max(0, m.start() - 25):m.start()]
                if not _PHONE_CONTEXT_RE.search(window):
                    continue
            out.append(Match(m.start(), m.end(), value, self.label, "PhoneDetector"))
        return out


PHONE_DETECTOR = PhoneDetector()

SSN_DETECTOR = RegexDetector(
    label="SSN",
    pattern=r"\b\d{3}-\d{2}-\d{4}\b",
)

CREDIT_CARD_DETECTOR = RegexDetector(
    label="CREDIT_CARD_NUMBER",
    pattern=r"\b\d(?:[ \-]?\d){12,18}\b",
    validator=_luhn_valid,
)

IPV4_DETECTOR = RegexDetector(
    label="IP_ADDRESS",
    pattern=r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
)

IPV6_DETECTOR = RegexDetector(
    label="IP_ADDRESS",
    pattern=r"\b(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}\b",
)

# DOB is scoped to an explicit context keyword. Without this, a DATE_TIME
# regex would flag every date in the document ("Dated December 10, 2025",
# "Companies Act, 2013", filing deadlines, etc.) -- exactly the kind of
# precision trap the assignment calls out re: "Order"/"Ticket" numbers.
DOB_DETECTOR = RegexDetector(
    label="DATE_OF_BIRTH",
    pattern=r"(?:Date\s+of\s+Birth|DOB|born\s+on)\s*[:\-]?\s*"
            r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
    flags=re.IGNORECASE,
    group=1,
)

class NERDetector(Detector):
    """Wraps spaCy NER for PERSON / ORG / GPE+LOC entities.

    Note on an approach we tried and dropped: this document (an Indian IPO
    prospectus) writes many names/orgs in ALL CAPS ("KUSHAL SUBBAYYA HEGDE"),
    and spaCy's recall drops sharply on all-caps spans since it's trained
    mostly on mixed-case text. We experimented with running NER a second
    time on a title-cased copy of each paragraph to recover these, but it
    introduced more false positives than it fixed (e.g. tagging a stray
    "Email" as PERSON) -- discarded in favor of the narrower
    `AllCapsListDetector` below, which targets the specific ALL-CAPS
    "PROMOTERS: NAME, NAME, ..." pattern this document type actually uses.
    """

    LABEL_MAP = {
        "PERSON": "FULL_NAME",
        "ORG": "COMPANY_NAME",
        "GPE": "ADDRESS",
        "LOC": "ADDRESS",
        "FAC": "ADDRESS",
    }

    # Single-token "names" that are almost always document field labels
    # ("Email:", "Tel:", "Website:") mis-tagged as PERSON by capitalization
    # alone. Filtering these is a precision fix, not a recall one -- multi
    # token spans are untouched.
    LABEL_STOPWORDS = {
        "email", "tel", "telephone", "website", "phone", "fax", "address",
        "contact", "date", "name", "title", "department", "office",
        "agency", "board", "chairman", "director", "promoter", "offer",
        "price", "share", "equity", "annexure", "schedule", "note",
    }

    # Regulatory/financial acronyms and legal-document boilerplate that
    # spaCy's NER frequently mis-tags as ORGANIZATION or PERSON in Indian
    # securities filings ("the SEBI ICDR Regulations", "RED HERRING",
    # "UPI", "Anchor Investors"). None of these identify a specific
    # sensitive company or person, so we drop a match if every
    # content-word in its span is drawn from this list.
    REGULATORY_NOISE = {
        "sebi", "icdr", "rbi", "fema", "upi", "asba", "qib", "qibs", "nii",
        "niis", "rii", "riis", "icai", "fii", "fpi", "nri", "pan", "gst",
        "cin", "din", "kyc", "ipo", "roc", "nse", "bse", "scrr", "scra",
        "sebi's", "red", "herring", "anchor", "investors", "regulations",
        "regulation", "act", "rules", "rule", "guidelines", "circular",
        "committee", "prospectus", "offer", "issue", "book", "running",
        "lead", "managers", "manager", "the", "of", "and", "for", "on",
    }

    def __init__(self, nlp):
        self.nlp = nlp

    def _is_regulatory_noise(self, text: str) -> bool:
        words = re.findall(r"[a-zA-Z']+", text.lower())
        return bool(words) and all(w in self.REGULATORY_NOISE for w in words)

    def detect(self, text: str) -> List[Match]:
        out = []
        for ent in self.nlp(text).ents:
            label = self.LABEL_MAP.get(ent.label_)
            if label is None:
                continue
            if (
                label == "FULL_NAME"
                and " " not in ent.text
                and ent.text.strip().lower() in self.LABEL_STOPWORDS
            ):
                continue
            if label in ("COMPANY_NAME", "FULL_NAME") and self._is_regulatory_noise(ent.text):
                continue
            out.append(Match(ent.start_char, ent.end_char, ent.text, label, "spaCy_NER"))
        return out


class AllCapsListDetector(Detector):
    """Targeted heuristic for a pattern specific to Indian regulatory
    filings: a section header like 'OUR PROMOTERS:' followed by a run of
    comma-separated ALL-CAPS names/entity names. spaCy's NER reliably
    misses these (see note above), but they are some of the single most
    sensitive PII in the document (the full list of beneficial owners), so
    it's worth a dedicated rule rather than relying on general NER.

    Each comma-separated segment is classified as ORGANIZATION if it
    contains a business-entity keyword (TRUST, LIMITED, PRIVATE, LLP...),
    otherwise PERSON.
    """

    TRIGGER = re.compile(r"\bPROMOTERS?\s*:?\s*", re.IGNORECASE)
    ORG_KEYWORDS = {
        "TRUST", "LIMITED", "PRIVATE", "PVT", "LLP", "LTD", "INC",
        "CORP", "COMPANY", "GROUP", "HOLDINGS", "FUND",
    }

    def detect(self, text: str) -> List[Match]:
        out = []
        for trigger in self.TRIGGER.finditer(text):
            start = trigger.end()
            end = start
            # walk forward while we stay inside an ALL-CAPS / comma / "AND" run
            while end < len(text) and re.match(r"[A-Z&.,\s]|(?<=\s)AND(?=\s|,|$)", text[end]):
                end += 1
                if end - start > 600:  # safety cap
                    break
            span_text = text[start:end].rstrip(" ,")
            if len(span_text) < 4:
                continue
            offset = start
            for segment in re.split(r",\s*|\s+AND\s+", span_text):
                seg = segment.strip()
                if len(seg) < 3:
                    offset += len(segment) + 1
                    continue
                seg_start = text.index(seg, offset)
                seg_end = seg_start + len(seg)
                label = "COMPANY_NAME" if any(k in seg.split() for k in self.ORG_KEYWORDS) else "FULL_NAME"
                out.append(Match(seg_start, seg_end, seg, label, "AllCapsListDetector"))
                offset = seg_end
        return out



class AddressBlockDetector(Detector):
    """spaCy's NER only recognizes place *names* (cities, states) inside an
    address -- it has no concept of a street number or building identifier
    ("11/3, 11/4, Village Birdewadi"), so it only ever catches part of an
    address. This detector instead looks at the whole paragraph: if it
    contains an Indian PIN code (6-digit postal code) or a clear
    address-only keyword (Village, Taluka, Gat No., Survey No., Plot No.),
    the *entire* paragraph is treated as one address, since in this
    document type address lines are their own dedicated paragraph/table
    cell and don't share space with unrelated sentences.
    """

    label = "ADDRESS"
    PIN_CODE_RE = re.compile(r"\b\d{3}\s?\d{3}\b")
    KEYWORD_RE = re.compile(
        r"\b(village|taluka|gat no\.?|survey no\.?|plot no\.?)\b", re.IGNORECASE
    )
    MAX_LEN = 200  # address paragraphs are short; a long narrative paragraph
                   # that happens to mention a PIN code or "Village" in
                   # passing should NOT be swallowed whole.

    def detect(self, text: str) -> List[Match]:
        stripped = text.strip()
        if not stripped or len(stripped) > self.MAX_LEN:
            return []
        if not (self.PIN_CODE_RE.search(stripped) or self.KEYWORD_RE.search(stripped)):
            return []
        start = text.index(stripped)
        return [Match(start, start + len(stripped), stripped, self.label, "AddressBlockDetector")]


def build_default_detectors(nlp) -> List[Detector]:
    """Registry of active detectors. Add new PII types here."""
    return [
        EMAIL_DETECTOR,
        PHONE_DETECTOR,
        SSN_DETECTOR,
        CREDIT_CARD_DETECTOR,
        IPV4_DETECTOR,
        IPV6_DETECTOR,
        DOB_DETECTOR,
        AddressBlockDetector(),
        NERDetector(nlp),
        AllCapsListDetector(),
    ]
