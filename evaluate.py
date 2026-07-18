from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List

import spacy

from defined_terms import extract_defined_terms
from detectors import build_default_detectors
from engine import RedactionEngine
from substitution import Substitutor

DOCX_PATH = "output\redacted_prospectus.docx"


def build_engine() -> RedactionEngine:
    nlp = spacy.load("en_core_web_lg", disable=["parser", "tagger", "lemmatizer", "attribute_ruler"])
    detectors = build_default_detectors(nlp)
    substitutor = Substitutor()
    defined_terms = extract_defined_terms(DOCX_PATH)
    return RedactionEngine(detectors, substitutor, defined_terms=defined_terms)


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


def evaluate():
    sample = json.load(open("ground_truth/sample_paragraphs.json"))
    gt = json.load(open("ground_truth/ground_truth.json"))

    text_by_idx = {s["idx"]: s["text"] for s in sample}
    gt_by_idx: Dict[int, List[dict]] = defaultdict(list)
    for g in gt:
        gt_by_idx[g["idx"]].append(g)

    engine = build_engine()

    strict = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    overlap = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    fp_examples = defaultdict(list)
    fn_examples = defaultdict(list)

    for idx, text in text_by_idx.items():
        matches = engine.find_matches(text)
        gts_raw = gt_by_idx.get(idx, [])

        # Locate each ground-truth string's span within the paragraph.
        # Sequential search-from-cursor handles repeated substrings
        # (e.g. the same trust name appearing twice in one paragraph).
        gt_spans = []
        cursor_by_text = defaultdict(int)
        for g in gts_raw:
            start_from = cursor_by_text[g["text"]]
            pos = text.find(g["text"], start_from)
            if pos == -1:
                pos = text.find(g["text"])  # fallback: search from the start
            cursor_by_text[g["text"]] = (pos + 1) if pos != -1 else start_from
            gt_spans.append({
                "type": g["type"], "text": g["text"],
                "start": pos if pos != -1 else None,
                "end": (pos + len(g["text"])) if pos != -1 else None,
                "matched_strict": False, "matched_overlap": False,
            })

        pred_spans = [
            {"type": m.label, "text": m.text, "start": m.start, "end": m.end,
             "matched_strict": False, "matched_overlap": False}
            for m in matches
        ]

        for g in gt_spans:
            for p in pred_spans:
                if not p["matched_strict"] and g["type"] == p["type"] and g["text"] == p["text"]:
                    g["matched_strict"] = p["matched_strict"] = True
                    break

        # Overlap scoring is intentionally NOT exclusive 1-to-1: several
        # predicted fragments can legitimately cover pieces of the same
        # ground-truth span (e.g. "Pune", "Maharashtra", and "India" all
        # correctly overlap one full address block). Recall asks "was
        # this gt span covered by at least one prediction?"; precision
        # asks "did this prediction land on real PII?" -- independently,
        # so redundant-but-correct coverage isn't miscounted as a miss.
        for g in gt_spans:
            if g["start"] is None:
                continue
            if any(g["type"] == p["type"] and _overlaps(g["start"], g["end"], p["start"], p["end"]) for p in pred_spans):
                g["matched_overlap"] = True
        for p in pred_spans:
            if any(g["type"] == p["type"] and g["start"] is not None and _overlaps(g["start"], g["end"], p["start"], p["end"]) for g in gt_spans):
                p["matched_overlap"] = True

        for g in gt_spans:
            t = g["type"]
            if g["matched_strict"]:
                strict[t]["tp"] += 1
            else:
                strict[t]["fn"] += 1
            if g["matched_overlap"]:
                overlap[t]["tp"] += 1
            else:
                overlap[t]["fn"] += 1
                fn_examples[t].append((idx, g["text"]))

        for p in pred_spans:
            t = p["type"]
            if not p["matched_strict"]:
                strict[t]["fp"] += 1
            if not p["matched_overlap"]:
                overlap[t]["fp"] += 1
                fp_examples[t].append((idx, p["text"]))

    return strict, overlap, fp_examples, fn_examples


def _metrics(stats: dict) -> dict:
    tp, fp, fn = stats["tp"], stats["fp"], stats["fn"]
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) and precision == precision and recall == recall and (precision + recall) > 0 else float("nan")
    accuracy = tp / (tp + fp + fn) if (tp + fp + fn) else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy}


def summarize(stats_by_type: dict) -> dict:
    out = {t: _metrics(s) for t, s in stats_by_type.items()}
    totals = {"tp": 0, "fp": 0, "fn": 0}
    for s in stats_by_type.values():
        for k in totals:
            totals[k] += s[k]
    out["OVERALL"] = _metrics(totals)
    return out


if __name__ == "__main__":
    strict, overlap, fp_ex, fn_ex = evaluate()
    print("=== PII Detection Accuracy ===")
    print("(a redaction counts as correct if it overlaps the correct answer)\n")
    for t, m in summarize(overlap).items():
        print(f"{t:15s} tp={m['tp']:3d} fp={m['fp']:3d} fn={m['fn']:3d}  "
              f"P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} Acc={m['accuracy']:.2f}")
