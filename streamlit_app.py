from __future__ import annotations

import json
import secrets
import tempfile
import time
from collections import Counter
from pathlib import Path

import spacy
import streamlit as st

from defined_terms import extract_defined_terms
from detectors import build_default_detectors
from docx_redactor import redact_docx
from engine import RedactionEngine
from substitution import Substitutor

DISABLE_PIPES = ["parser", "tagger", "lemmatizer", "attribute_ruler"]
MODEL_CANDIDATES = ["en_core_web_lg", "en_core_web_md", "en_core_web_sm"]


@st.cache_resource(show_spinner=False)
def load_nlp_model() -> tuple[spacy.language.Language, str]:
    last_error: Exception | None = None
    for model_name in MODEL_CANDIDATES:
        try:
            nlp = spacy.load(model_name, disable=DISABLE_PIPES)
            return nlp, model_name
        except Exception as exc:  # pragma: no cover - best effort fallback
            last_error = exc
    raise RuntimeError(
        "No spaCy English model found. Install en_core_web_sm or en_core_web_lg in requirements.txt"
    ) from last_error


def build_engine(input_path: str, seed: int) -> tuple[RedactionEngine, str, int]:
    nlp, model_name = load_nlp_model()
    detectors = build_default_detectors(nlp)
    substitutor = Substitutor(seed=seed)
    defined_terms = extract_defined_terms(input_path)
    engine = RedactionEngine(detectors, substitutor, defined_terms=defined_terms)
    return engine, model_name, len(defined_terms)


def summarize_audit(audit_log: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(item["type"] for item in audit_log).items(), key=lambda kv: (-kv[1], kv[0])))


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

            :root {
                --bg-0: #070b14;
                --bg-1: #0e1526;
                --bg-2: #131e32;
                --card: rgba(18, 27, 44, 0.78);
                --card-border: rgba(128, 150, 195, 0.24);
                --text: #e6edf9;
                --muted: #9fb0ce;
            }

            .stApp {
                font-family: 'Space Grotesk', sans-serif;
                color: var(--text);
                background:
                    radial-gradient(900px 500px at 8% -12%, rgba(60, 141, 255, 0.18), transparent 62%),
                    linear-gradient(160deg, var(--bg-0), var(--bg-1) 45%, var(--bg-2));
            }

            header[data-testid="stHeader"] {
                background: rgba(7, 11, 20, 0.58);
                backdrop-filter: blur(6px);
            }

            [data-testid="stToolbar"] {
                top: 0.35rem;
            }

            .block-container {
                max-width: 980px;
                padding-top: 5.4rem;
                padding-bottom: 3rem;
                padding-left: 2rem;
                padding-right: 2rem;
            }

            .hero {
                border: 1px solid var(--card-border);
                border-radius: 16px;
                background: var(--card);
                box-shadow: 0 10px 26px rgba(0, 0, 0, 0.24);
                padding: 1.35rem 1.35rem;
                margin-bottom: 1.2rem;
            }

            .hero h1 {
                margin: 0 0 0.4rem 0;
                letter-spacing: 0.01em;
                font-size: 1.95rem;
            }

            .hero p {
                margin: 0;
                color: var(--muted);
                font-size: 0.98rem;
                max-width: 760px;
            }

            .workflow-panel {
                border: 1px solid var(--card-border);
                border-radius: 14px;
                background: var(--card);
                box-shadow: 0 8px 22px rgba(0, 0, 0, 0.2);
                padding: 1.1rem;
                margin-bottom: 1.05rem;
            }

            .panel-title {
                margin: 0 0 0.35rem 0;
                font-size: 1.03rem;
                color: #deebff;
            }

            .panel-copy {
                margin: 0;
                color: var(--muted);
                font-size: 0.93rem;
                line-height: 1.45;
            }

            .settings-grid {
                margin-top: 0.65rem;
            }

            .uploader-wrap {
                margin-top: 0.45rem;
            }

            [data-testid="stFileUploader"] {
                border: 1px dashed rgba(130, 155, 200, 0.6);
                border-radius: 12px;
                background: rgba(15, 23, 40, 0.52);
                padding: 0.45rem;
                margin-top: 0.2rem;
                margin-bottom: 0.9rem;
            }

            .results-wrap {
                border: 1px solid var(--card-border);
                border-radius: 14px;
                background: rgba(12, 20, 36, 0.82);
                padding: 1rem;
                margin-top: 1rem;
            }

            [data-testid="stMetric"] {
                border: 1px solid var(--card-border);
                border-radius: 12px;
                background: var(--card);
                backdrop-filter: blur(8px);
                padding: 0.2rem 0.7rem;
            }

            .stButton > button,
            .stDownloadButton > button {
                border-radius: 10px;
                border: 1px solid rgba(79, 195, 255, 0.55);
                background: linear-gradient(120deg, rgba(50, 132, 255, 0.22), rgba(53, 214, 166, 0.24));
                color: #e8f2ff;
                font-weight: 600;
                transition: all 0.22s ease;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                border-color: rgba(86, 219, 241, 0.92);
                transform: translateY(-1px);
                box-shadow: 0 10px 24px rgba(0, 0, 0, 0.30);
            }

            .stTable table {
                border-radius: 10px;
                overflow: hidden;
            }

            .stCode, code {
                font-family: 'IBM Plex Mono', monospace;
            }

            @media (max-width: 720px) {
                .block-container {
                    padding-top: 6rem;
                    padding-left: 1rem;
                    padding-right: 1rem;
                }
                .hero h1 { font-size: 1.5rem; }
                .hero p { font-size: 0.94rem; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1>PII Redaction Studio</h1>
            <p>Upload a DOCX, run redaction, and download the cleaned file with optional audit output.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_settings_panel() -> tuple[bool, int]:
    st.markdown(
        """
        <div class="workflow-panel">
            <h2 class="panel-title">Processing Settings</h2>
            <p class="panel-copy">Use deterministic mode for reproducible runs. Disable it when you want new fake values every time.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    include_col, mode_col, seed_col = st.columns([0.95, 1.1, 1.05], gap="medium")
    with include_col:
        include_audit = st.toggle("Generate audit log", value=True)

    with mode_col:
        deterministic_mode = st.toggle(
            "Deterministic replacements",
            value=True,
            help="When enabled, the same source values generate the same fake values across reruns.",
        )

    seed = 42
    with seed_col:
        if deterministic_mode:
            seed = int(
                st.number_input(
                    "Seed",
                    min_value=0,
                    max_value=1_000_000,
                    value=42,
                    step=1,
                    help="Use a fixed seed for reproducible outputs.",
                )
            )
        else:
            seed = secrets.randbelow(1_000_000_000)
            st.caption("Randomized mode: a new hidden seed is used on every run.")

    st.caption(
        "Seed controls reproducibility, not security. Keep deterministic mode ON for QA/demo consistency."
    )
    st.markdown("<div style='height: 0.7rem;'></div>", unsafe_allow_html=True)
    return include_audit, seed


def main() -> None:
    st.set_page_config(page_title="PII Redaction Tool", page_icon="PII", layout="wide")
    inject_custom_css()
    render_hero()

    include_audit, seed = render_settings_panel()

    st.markdown(
        """
        <div class="workflow-panel uploader-wrap">
            <h2 class="panel-title">Upload Document</h2>
            <p class="panel-copy">Select a DOCX file to redact. Processing uses temporary runtime storage only.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader("Upload a DOCX file", type=["docx"])

    if uploaded_file is None:
        st.info("Add a DOCX file to start the redaction workflow.")
        return

    st.write(f"Selected file: **{uploaded_file.name}**")

    if st.button("Redact Document", type="primary", use_container_width=True):
        start_time = time.time()
        with st.spinner("Redacting document..."):
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_root = Path(temp_dir)
                    input_path = temp_root / uploaded_file.name
                    output_path = temp_root / f"redacted_{uploaded_file.name}"

                    input_path.write_bytes(uploaded_file.getvalue())

                    engine, model_name, defined_term_count = build_engine(str(input_path), int(seed))
                    audit_log = redact_docx(str(input_path), str(output_path), engine)
                    redacted_bytes = output_path.read_bytes()

                    elapsed = time.time() - start_time
                    by_type = summarize_audit(audit_log)

                    st.markdown("<div class='results-wrap'>", unsafe_allow_html=True)
                    st.success("Redaction complete")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("PII Detected", len(audit_log))
                    col2.metric("Defined Terms", defined_term_count)
                    col3.metric("Runtime", f"{elapsed:.2f}s")
                    col4.metric("NLP Model", model_name)

                    if by_type:
                        st.subheader("Redactions by Type")
                        st.table([{"PII Type": pii_type, "Count": count} for pii_type, count in by_type.items()])
                    else:
                        st.info("No redactions were detected in this file.")

                    download_col1, download_col2 = st.columns(2)
                    with download_col1:
                        st.download_button(
                            label="Download Redacted DOCX",
                            data=redacted_bytes,
                            file_name=output_path.name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                        )

                    if include_audit:
                        audit_json = json.dumps(audit_log, indent=2).encode("utf-8")
                        with download_col2:
                            st.download_button(
                                label="Download Audit Log (JSON)",
                                data=audit_json,
                                file_name="audit_log.json",
                                mime="application/json",
                                use_container_width=True,
                            )

                    st.caption(
                        "Privacy note: this demo processes your uploaded document on the hosted app runtime. "
                        "Do not upload highly sensitive production data unless your compliance requirements are met."
                    )
                    st.markdown("</div>", unsafe_allow_html=True)
            except Exception as exc:
                st.error(f"Redaction failed: {exc}")
                st.exception(exc)


if __name__ == "__main__":
    main()
