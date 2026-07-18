# PII Redaction Tool

A Python-based tool that detects personally identifiable information (PII)
in a Word document and replaces it with realistic, consistent synthetic
values.

The system is designed for Red Herring Prospectus-style text, where named
entities (person names, company names, addresses) appear in varied legal and
business prose.


## Overview

This project identifies sensitive values in text and redacts them by
substituting each original value with a stable fake replacement.

- The same original value always maps to the same fake value.
- Different originals map to different fakes.
- The output remains readable and internally consistent.

## Features

- Hybrid detection pipeline (regex + NLP)
- Consistent substitution for repeated entities
- DOCX redaction support
- Audit log support for traceability
- Built-in evaluation script and detector unit tests

## PII Types Covered

| Assignment asked for | Label used in code/output |
|---|---|
| Full names | `FULL_NAME` |
| Email addresses | `EMAIL_ADDRESS` |
| Phone numbers | `PHONE_NUMBER` |
| Company names | `COMPANY_NAME` |
| Physical/mailing addresses | `ADDRESS` |
| Social Security Numbers | `SSN` |
| Credit card numbers | `CREDIT_CARD_NUMBER` |
| Dates of birth | `DATE_OF_BIRTH` |
| IP addresses | `IP_ADDRESS` |

## How It Works

- **Regex detectors** handle fixed-format entities:
  email addresses, phone numbers, SSNs, credit card numbers, IP addresses,
  and dates of birth.
- **spaCy-based NLP detectors** handle context-dependent entities:
  full names, company names, and addresses.
- **Substitution engine** ensures deterministic mapping:
  one unique fake per unique original value, reused across the document.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### 1. Redact a document

```bash
python3 main.py <input.docx> <output.docx> [audit_log.json]
```

Example:

```bash
python3 main.py input.docx redacted_output.docx output/audit_log.json
```

### 2. Evaluate detector performance

```bash
python3 evaluate.py
```

### 3. Run tests

```bash
python3 -m pytest tests/test_detectors.py
```

## Streamlit App

This repository includes a Streamlit UI in `streamlit_app.py` that lets you:

- Upload a DOCX file
- Run PII redaction
- Download the redacted DOCX
- Optionally download an audit JSON log

Run locally:

```bash
streamlit run streamlit_app.py
```

Notes:

- The app tries spaCy models in this order: `en_core_web_lg`, then `en_core_web_md`, then `en_core_web_sm`.
- `requirements.txt` includes `en_core_web_sm` so deployment works on free tiers.

## Evaluation

Measured against 186 hand-checked PII instances from a representative sample
of the source document:

| PII Type | Precision | Recall | F1 |
|---|---|---|---|
| Email address | 1.00 | 1.00 | 1.00 |
| Phone number | 1.00 | 1.00 | 1.00 |
| Full name | 0.91 | 0.84 | 0.88 |
| Company name | 0.71 | 0.90 | 0.79 |
| Address | 0.51 | 0.90 | 0.66 |
| **Overall** | **0.74** | **0.89** | **0.81** |

For full methodology and error analysis, see `EVALUATION_REPORT.md`.

## Known Limitations

- Street/plot numbers embedded inside long narrative lines can be missed,
  even when nearby city/state text is detected.
- Some company names containing place-like words (for example, "Park") may
  be mislabeled as addresses instead of companies.
- SSN, credit card, IP address, and date-of-birth detectors are validated
  through synthetic unit tests because these values do not appear in the
  provided corporate filing data.

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Entry point for document redaction |
| `streamlit_app.py` | Streamlit frontend + app flow for upload/redact/download |
| `engine.py` | Orchestrates detection and substitution |
| `detectors.py` | PII detector implementations |
| `substitution.py` | Generates deterministic fake replacements |
| `docx_redactor.py` | Applies redactions to DOCX content |
| `defined_terms.py` | Loads domain terms to reduce false positives |
| `evaluate.py` | Runs evaluation against ground truth |
| `tests/test_detectors.py` | Unit tests for detector behavior |
| `requirements.txt` | Runtime dependencies for local/dev and Streamlit deploy |
| `.streamlit/config.toml` | Streamlit app settings (theme and upload size) |
| `ground_truth/` | Ground-truth labels for evaluation |
| `output/audit_log.json` | Example audit log output |
| `EVALUATION_REPORT.md` | Detailed metrics and analysis |

## Extending to a New PII Type

1. Add a detector in `detectors.py` (regex-based or NLP-based).
2. Register it in `build_default_detectors()`.
3. Add a fake-value generation method in `substitution.py`.
4. Add/expand tests in `tests/test_detectors.py`.
