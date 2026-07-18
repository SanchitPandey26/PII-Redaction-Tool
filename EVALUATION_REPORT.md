# Evaluation Report

## How this was tested

Manually checking all ~5,200 paragraphs wasn't realistic in the time
available, so I hand-labeled the correct answers for a **223-paragraph
sample** (`ground_truth/`) covering four different parts of the document
(cover page, contact details, the promoters list, and the glossary
section) — 186 individual pieces of PII in total, checked by hand.

The tool's output on those same paragraphs was then compared against the
hand-checked answers to calculate:

- **Precision** — of everything the tool redacted, how much was actually
  real PII (not a false alarm)?
- **Recall** — of all the real PII that was actually there, how much did
  the tool catch?
- **F1** — one combined score balancing the two.

A redaction counts as correct if it overlaps the correct answer (rather
than requiring a perfect word-for-word match), since what actually matters
for privacy is whether the sensitive text is gone from the document, not
whether the boundary is pixel-perfect.

SSNs, credit cards, IP addresses, and dates of birth don't appear anywhere
in this document at all (it's a company filing, not personal records), so
those four are tested separately with made-up example sentences instead —
see `tests/test_detectors.py`.

## Results

| PII Type | Precision | Recall | F1 |
|---|---|---|---|
| Email address | 1.00 | 1.00 | 1.00 |
| Phone number | 1.00 | 1.00 | 1.00 |
| Full name | 0.91 | 0.84 | 0.88 |
| Company name | 0.71 | 0.90 | 0.79 |
| Address | 0.51 | 0.90 | 0.66 |
| **Overall** | **0.74** | **0.89** | **0.81** |

## What this means in plain terms

- **Emails and phone numbers are essentially solved.** Fixed format, so
  there's little room for error.
- **Names are strong** (88% F1) — the main gap is the same name
  occasionally missed in one unusual sentence, even though it's caught
  correctly everywhere else it appears.
- **Company names are good** (79% F1) — the main error is a building name
  like "Montreal Business Centre" occasionally getting filed under
  Address instead of Company Name. The text still gets hidden either way;
  it's just mislabeled.
- **Addresses are the weakest type** (66% F1). A full street address mixes
  a place name ("Pune") that's easy to recognize with a building/plot
  number ("11/3, Village Birdewadi") that doesn't look like a name at
  all, so it's genuinely harder to catch as one clean unit.

## Remaining gap

When an address is written *inside* a longer sentence rather than on its
own dedicated line (e.g. "...and its Registered Office at 11/3, Village
Birdewadi, Pune, Maharashtra, India."), the tool still only catches the
place names, not the street/plot number — the whole-line rule above
doesn't apply there, since it would risk redacting the rest of the
sentence too. This is the single biggest thing to improve next, and would
realistically need a proper address-parsing library rather than a bigger
version of the same heuristic.
