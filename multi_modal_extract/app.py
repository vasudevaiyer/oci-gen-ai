from __future__ import annotations

import base64
import os
from typing import Any

import streamlit as st

from oci_multimodal_service import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_PROFILE,
    MODEL_PRESETS,
    AppConfigError,
    flatten_json_leaves,
    get_config_summary,
    run_extraction,
)


DEFAULT_PROMPT = """Extract the visible content from these images and return only valid JSON.
Focus on OCR text, headings, lists, tables, labels, stamps, handwritten notes, and form-like key/value pairs.
If the upload is a PDF, treat each rendered page as one page in the response.
"""


def decode_data_url(data_url: str) -> bytes:
    encoded = data_url.split(",", 1)[1]
    return base64.b64decode(encoded)


def render_original_preview(file_name: str, file_bytes: bytes, mime_type: str | None) -> None:
    detected_mime = mime_type or ""
    if detected_mime == "application/pdf" or file_name.lower().endswith(".pdf"):
        encoded = base64.b64encode(file_bytes).decode("utf-8")
        st.markdown(
            f"""
            <iframe
                src="data:application/pdf;base64,{encoded}"
                width="100%"
                height="720"
                type="application/pdf">
            </iframe>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.image(file_bytes, caption=file_name, use_container_width=True)


def display_metric_value(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(248, 214, 149, 0.35), transparent 30%),
                radial-gradient(circle at top right, rgba(139, 194, 170, 0.22), transparent 26%),
                linear-gradient(180deg, #f7f2e8 0%, #efe6d8 100%);
        }
        h1, h2, h3 {
            font-family: Georgia, "Times New Roman", serif;
            letter-spacing: 0.02em;
        }
        html, body, [class*="css"] {
            font-family: "Trebuchet MS", Verdana, sans-serif;
        }
        .hero-card {
            background: rgba(255, 251, 244, 0.82);
            border: 1px solid rgba(123, 94, 58, 0.18);
            border-radius: 20px;
            padding: 1.1rem 1.2rem;
            box-shadow: 0 12px 30px rgba(86, 62, 31, 0.08);
            margin-bottom: 1rem;
        }
        .metric-chip {
            display: inline-block;
            margin-right: 0.55rem;
            margin-bottom: 0.55rem;
            padding: 0.4rem 0.7rem;
            border-radius: 999px;
            background: #173f35;
            color: #f8f7f2;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div class="hero-card">
            <h1>OCI Multimodal Extract Compare</h1>
            <p>Upload an image or PDF, pick an OCI-hosted GenAI vision model, and inspect the extracted JSON response.</p>
            <span class="metric-chip">Cohere</span>
            <span class="metric-chip">Gemini Flash</span>
            <span class="metric-chip">Meta Llama Vision</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar() -> dict[str, Any]:
    st.sidebar.header("OCI Settings")
    config_path = st.sidebar.text_input("OCI config path", value=DEFAULT_CONFIG_PATH)
    config_summary = get_config_summary(config_path, DEFAULT_PROFILE)

    if config_summary.profiles:
        default_index = config_summary.profiles.index(config_summary.selected_profile)
        profile = st.sidebar.selectbox("Config profile", config_summary.profiles, index=default_index)
        config_summary = get_config_summary(config_path, profile)
    else:
        profile = st.sidebar.text_input("Config profile", value=DEFAULT_PROFILE)
        st.sidebar.warning("No OCI profiles were found in the config file. You can still fill the fields manually.")

    endpoint = st.sidebar.text_input("Inference endpoint", value=config_summary.endpoint)
    default_compartment = os.getenv("OCI_COMPARTMENT_OCID", config_summary.default_compartment_id)
    compartment_id = st.sidebar.text_input("Compartment OCID", value=default_compartment)

    st.sidebar.caption(f"Resolved region: `{config_summary.region}`")
    st.sidebar.caption(f"Config file present: `{config_summary.has_config}`")

    return {
        "config_path": config_path,
        "profile": profile,
        "endpoint": endpoint,
        "compartment_id": compartment_id,
    }


def main() -> None:
    st.set_page_config(page_title="OCI Vision Model Compare", page_icon=":page_facing_up:", layout="wide")
    apply_theme()
    render_header()
    settings = sidebar()

    left, right = st.columns([1.1, 1.2], gap="large")

    with left:
        st.subheader("Input")
        uploaded_file = st.file_uploader(
            "Upload an image or PDF",
            type=["pdf", "png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"],
        )

        selected_models = st.multiselect(
            "Models",
            list(MODEL_PRESETS.keys()),
            default=list(MODEL_PRESETS.keys()),
        )
        if len(selected_models) == 1:
            selected_preset = MODEL_PRESETS[selected_models[0]]
            custom_model_id = st.text_input("Model ID override", value=selected_preset["model_id"])
            st.caption(selected_preset["notes"])
        else:
            custom_model_id = ""
            st.caption("Multiple presets selected. Each model will run with its configured OCI model ID.")

        with st.expander("Extraction Prompt", expanded=True):
            user_prompt = st.text_area("Prompt", value=DEFAULT_PROMPT, height=160)

        pdf_col, token_col, temp_col = st.columns(3)
        with pdf_col:
            max_pdf_pages = st.slider("PDF pages", min_value=1, max_value=12, value=4)
        with token_col:
            max_output_tokens = st.slider("Max output tokens", min_value=256, max_value=4096, value=1400, step=64)
        with temp_col:
            temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.1, step=0.1)

        pdf_dpi = st.slider("PDF render DPI", min_value=96, max_value=220, value=144, step=12)

        run_clicked = st.button(
            "Run Compare",
            type="primary",
            use_container_width=True,
            disabled=uploaded_file is None or not selected_models,
        )

        if uploaded_file is not None:
            file_kind = uploaded_file.type or uploaded_file.name.rsplit(".", 1)[-1]
            st.info(f"Selected file: `{uploaded_file.name}` ({file_kind})")
            with st.expander("Original Upload Preview", expanded=False):
                render_original_preview(uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)

    with right:
        st.subheader("Output")
        result_slot = st.container()

        if uploaded_file is None:
            result_slot.info("Upload a PDF or image to start a model run.")
            return

        if run_clicked:
            batch_results: dict[str, Any] = {}
            batch_errors: dict[str, str] = {}
            upload_bytes = uploaded_file.getvalue()

            for model_label in selected_models:
                preset = MODEL_PRESETS[model_label]
                model_id = custom_model_id.strip() if len(selected_models) == 1 and custom_model_id.strip() else preset["model_id"]
                with st.spinner(f"Calling OCI Generative AI for {model_label}..."):
                    try:
                        batch_results[model_label] = run_extraction(
                            config_path=settings["config_path"],
                            profile=settings["profile"],
                            compartment_id=settings["compartment_id"],
                            endpoint=settings["endpoint"],
                            model_id=model_id,
                            api_mode=preset["api_mode"],
                            uploaded_name=uploaded_file.name,
                            uploaded_mime_type=uploaded_file.type,
                            uploaded_bytes=upload_bytes,
                            max_pdf_pages=max_pdf_pages,
                            pdf_dpi=pdf_dpi,
                            user_prompt=user_prompt.strip(),
                            max_output_tokens=max_output_tokens,
                            temperature=temperature,
                        )
                    except (AppConfigError, RuntimeError) as exc:
                        batch_errors[model_label] = str(exc)

            st.session_state["last_results"] = batch_results
            st.session_state["last_errors"] = batch_errors

        errors = st.session_state.get("last_errors", {})
        results = st.session_state.get("last_results", {})

        if errors:
            for model_label, error_text in errors.items():
                result_slot.error(f"{model_label}: {error_text}")

        if not results:
            return

        summary_rows = []
        for model_label, result in results.items():
            req = result["request"]
            summary_rows.append(
                {
                    "model": model_label,
                    "model_id": req["model_id"],
                    "api_mode": req["api_mode"],
                    "rendered_pages": req["rendered_pages"],
                    "elapsed_ms": result["timing"]["elapsed_ms"],
                    "json_status": "repaired" if result["parsed_json"] is not None and result["parse_error"] else (
                        "ok" if result["parsed_json"] is not None else "failed"
                    ),
                }
            )

        st.dataframe(summary_rows, use_container_width=True, hide_index=True)

        model_tabs = st.tabs(list(results.keys()) + ["Preview"])
        model_labels = list(results.keys())
        for index, model_label in enumerate(model_labels):
            result = results[model_label]
            req = result["request"]
            with model_tabs[index]:
                metric_a, metric_b, metric_c = st.columns(3)
                metric_a.metric("Model ID", req["model_id"])
                metric_b.metric("Rendered pages", req["rendered_pages"])
                metric_c.metric("Elapsed ms", result["timing"]["elapsed_ms"])

                detail_tabs = st.tabs(["Extracted Fields", "Parsed JSON", "Raw Text", "Raw Response"])
                with detail_tabs[0]:
                    if result["parsed_json"] is not None:
                        extracted_fields = flatten_json_leaves(result["parsed_json"])
                        field_rows = [{"field": path, "value": value} for path, value in extracted_fields.items()]
                        st.dataframe(field_rows, use_container_width=True, hide_index=True)
                    else:
                        st.warning("No parsed JSON is available, so extracted fields could not be listed.")
                with detail_tabs[1]:
                    if result["parsed_json"] is not None:
                        if result["parse_error"]:
                            st.info(result["parse_error"])
                        st.json(result["parsed_json"])
                    else:
                        st.warning(result["parse_error"] or "The model response was not valid JSON.")
                with detail_tabs[2]:
                    st.code(result["raw_text"] or "(empty response)", language="json")
                with detail_tabs[3]:
                    st.json(result["raw_response"])

        with model_tabs[-1]:
            preview_tabs = st.tabs(["Original Upload", "Rendered Pages"])
            with preview_tabs[0]:
                render_original_preview(uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
            with preview_tabs[1]:
                first_result = next(iter(results.values()))
                for preview in first_result["preview_images"]:
                    st.image(
                        decode_data_url(preview["data_url"]),
                        caption=f"Rendered page {preview['page_number']}",
                        use_container_width=True,
                    )


if __name__ == "__main__":
    main()
