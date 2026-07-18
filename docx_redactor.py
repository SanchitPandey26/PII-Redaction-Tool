from __future__ import annotations
from typing import List
import docx
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from engine import RedactionEngine


def _redact_paragraph(paragraph: Paragraph, engine: RedactionEngine, audit_log: List[dict]) -> None:
    original_text = paragraph.text
    if not original_text.strip():
        return

    redacted_text, audit = engine.redact(original_text)
    if not audit:
        return  # nothing found, leave the paragraph untouched (byte-identical)

    audit_log.extend(audit)

    if not paragraph.runs:
        return

    # Write the full redacted string into the first run, blank the rest.
    paragraph.runs[0].text = redacted_text
    for run in paragraph.runs[1:]:
        run.text = ""


def _iter_paragraphs(container, _seen_cells: set | None = None) -> List[Paragraph]:
    if _seen_cells is None:
        _seen_cells = set()

    paragraphs: List[Paragraph] = list(container.paragraphs)
    for table in getattr(container, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                cell_key = id(cell._tc)
                if cell_key in _seen_cells:
                    continue
                _seen_cells.add(cell_key)
                paragraphs.extend(_iter_paragraphs(cell, _seen_cells))
    return paragraphs


def redact_docx(input_path: str, output_path: str, engine: RedactionEngine) -> List[dict]:
    document: DocumentObject = docx.Document(input_path)

    audit_log: List[dict] = []
    for paragraph in _iter_paragraphs(document):
        _redact_paragraph(paragraph, engine, audit_log)

    # Headers / footers (registered office addresses, contact emails, etc.
    # sometimes live here too).
    for section in document.sections:
        for hf in (section.header, section.footer):
            for paragraph in _iter_paragraphs(hf):
                _redact_paragraph(paragraph, engine, audit_log)

    document.save(output_path)
    return audit_log
