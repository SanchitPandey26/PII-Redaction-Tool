from __future__ import annotations

import json
import sys
import time

import spacy

from detectors import build_default_detectors
from defined_terms import extract_defined_terms
from docx_redactor import redact_docx
from engine import RedactionEngine
from substitution import Substitutor


def build_engine(input_path: str, seed: int = 42) -> RedactionEngine:
    # Only the NER component is needed -- disabling the parser/tagger/
    # lemmatizer roughly triples throughput on a document this size
    # (thousands of table-cell paragraphs) with no loss of NER accuracy,
    # since spaCy's NER head doesn't depend on those other pipes at
    # inference time for this model.
    nlp = spacy.load("en_core_web_lg", disable=["parser", "tagger", "lemmatizer", "attribute_ruler"])
    detectors = build_default_detectors(nlp)
    substitutor = Substitutor(seed=seed)
    defined_terms = extract_defined_terms(input_path)
    print(f"  extracted {len(defined_terms)} defined terms from the document's own glossary")
    return RedactionEngine(detectors, substitutor, defined_terms=defined_terms)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 main.py <input.docx> <output.docx> [audit_log.json]")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]
    audit_path = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"Loading NLP pipeline...")
    t0 = time.time()
    engine = build_engine(input_path)
    print(f"  done in {time.time() - t0:.1f}s")

    print(f"Redacting {input_path} ...")
    t0 = time.time()
    audit_log = redact_docx(input_path, output_path, engine)
    print(f"  done in {time.time() - t0:.1f}s -- {len(audit_log)} PII instances redacted")
    print(f"Redacted document written to {output_path}")

    if audit_path:
        with open(audit_path, "w") as f:
            json.dump(audit_log, f, indent=2)
        print(f"Audit log written to {audit_path}")

    by_type = {}
    for entry in audit_log:
        by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1
    print("\nRedactions by type:")
    for t, c in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {t:15s} {c}")


if __name__ == "__main__":
    main()
