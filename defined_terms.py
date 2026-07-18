from __future__ import annotations
import re
from typing import Set

import docx


def _normalize(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    normalized = re.sub(r"^(the|our|this|its)\s+", "", normalized)
    return normalized


def extract_defined_terms(docx_path: str) -> Set[str]:
    document = docx.Document(docx_path)
    terms: Set[str] = set()

    for table in document.tables:
        if not table.rows:
            continue
        header_cells = [c.text.strip().lower() for c in table.rows[0].cells]
        looks_like_glossary = any("term" in h for h in header_cells) and any(
            "description" in h for h in header_cells
        )
        if not looks_like_glossary:
            continue
        for row in table.rows[1:]:
            if not row.cells:
                continue
            raw = row.cells[0].text.strip()
            raw = re.sub(r"\s+", " ", raw)
            if not raw or len(raw) > 80:
                continue
            # entries like "Board/ Board of Directors" define several
            # interchangeable synonyms in one row -- split them out
            raw_normalized = _normalize(raw)
            if raw_normalized:
                terms.add(raw_normalized)  # combined form, e.g. "aoa/articles of association" --
                                            # NER sometimes spans the whole "X/Y" cell as one entity
            for variant in raw.split("/"):
                variant = variant.strip(" .")
                if variant:
                    terms.add(_normalize(variant))

    # A handful of universal non-PII tokens that show up across virtually
    # any financial document and aren't worth a glossary lookup, plus
    # generic professional-designation / role words that NER tags as ORG
    # even when the specific named entity next to them ("Kirtane & Pandit
    # LLP, Chartered Accountants") is already caught separately.
    terms |= {
        "n.a.", "n/a", "nil", "na", "fiscal", "fiscals",
        "registrar", "chartered accountants", "company secretary",
    }
    return terms


def is_defined_term(text: str, stoplist: Set[str]) -> bool:
    return _normalize(text) in stoplist
