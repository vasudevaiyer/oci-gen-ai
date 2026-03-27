from __future__ import annotations

import base64
import configparser
import json
import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from difflib import SequenceMatcher

import fitz
import oci
from dotenv import dotenv_values
from json_repair import repair_json
from oci.exceptions import ConfigFileNotFound, InvalidConfig, ServiceError
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    ChatDetails,
    CohereChatRequestV2,
    CohereImageContentV2,
    CohereImageUrlV2,
    CohereSystemMessageV2,
    CohereTextContentV2,
    CohereUserMessageV2,
    GenericChatRequest,
    ImageContent,
    ImageUrl,
    OnDemandServingMode,
    SystemMessage,
    TextContent,
    UserMessage,
)


DEFAULT_CONFIG_PATH = "/home/opc/.oci/config"
DEFAULT_PROFILE = "DEFAULT"
DEFAULT_REGION = "us-chicago-1"
DEFAULT_ENDPOINT_TEMPLATE = "https://inference.generativeai.{region}.oci.oraclecloud.com"
ENV_FALLBACK_PATHS = [Path(__file__).with_name(".env")]

MODEL_PRESETS = {
    "Cohere Command A Vision": {
        "model_id": "cohere.command-a-vision",
        "api_mode": "cohere_v2",
        "notes": "Enterprise-oriented image and document understanding through Cohere V2 chat.",
    },
    "Google Gemini 2.5 Flash": {
        "model_id": "google.gemini-2.5-flash",
        "api_mode": "generic",
        "notes": "Fast multimodal reasoning model through the generic chat API.",
    },
    "Meta Llama 3.2 90B Vision Instruct": {
        "model_id": "meta.llama-3.2-90b-vision-instruct",
        "api_mode": "generic",
        "notes": "Vision-capable Meta model for image understanding through the generic chat API.",
    },
}

SYSTEM_PROMPT = """You are an OCR and document-understanding assistant.
Extract only content supported by the uploaded visual input.
Return only valid JSON with this shape:
{
  "summary": "short summary",
  "pages": [
    {
      "page_number": 1,
      "text": "verbatim text where possible",
      "tables": [],
      "key_values": [],
      "entities": [],
      "notes": []
    }
  ]
}
Rules:
- Do not wrap JSON in markdown fences.
- Preserve visible wording as faithfully as possible.
- If a field is unavailable, return an empty string or empty list.
- For a single image, still return one item in pages.
- Keep tables as arrays of row objects when obvious; otherwise use notes.
"""


@dataclass(frozen=True)
class ConfigSummary:
    path: str
    profiles: list[str]
    selected_profile: str
    region: str
    endpoint: str
    default_compartment_id: str
    has_config: bool


class AppConfigError(RuntimeError):
    """Raised when OCI config is missing or incomplete for the app's needs."""


def list_profiles(config_path: str) -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(config_path)
    profiles = parser.sections()
    if parser.defaults() and DEFAULT_PROFILE not in profiles:
        profiles.insert(0, DEFAULT_PROFILE)
    return profiles


def _clean_config_value(value: str) -> str:
    cleaned = value.strip()
    if "#" in cleaned:
        cleaned = cleaned.split("#", 1)[0].strip()
    cleaned = cleaned.rstrip(",").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _lookup_parser_value(parser: configparser.ConfigParser, profile: str, option: str, fallback: str = "") -> str:
    option_lc = option.lower()
    if profile != DEFAULT_PROFILE and parser.has_section(profile):
        value = parser.get(profile, option_lc, fallback="")
        if value:
            return _clean_config_value(value)
    value = parser.defaults().get(option_lc, "")
    if value:
        return _clean_config_value(value)
    return fallback


def _read_env_fallbacks() -> dict[str, str]:
    for path in ENV_FALLBACK_PATHS:
        if path.exists():
            values = dotenv_values(path)
            return {key: str(value).strip() for key, value in values.items() if value is not None}
    return {}


def get_config_summary(config_path: str, profile: str = DEFAULT_PROFILE) -> ConfigSummary:
    parser = configparser.ConfigParser()
    parser.read(config_path)
    profiles = list_profiles(config_path)
    has_config = Path(config_path).exists() and (bool(parser.defaults()) or bool(parser.sections()))
    env_fallbacks = _read_env_fallbacks()

    selected = profile if parser.has_section(profile) else (profiles[0] if profiles else profile)
    if selected == DEFAULT_PROFILE and parser.defaults():
        selected = DEFAULT_PROFILE

    region = _lookup_parser_value(parser, selected, "region", DEFAULT_REGION) or DEFAULT_REGION
    endpoint = _lookup_parser_value(
        parser,
        selected,
        "OCI_GENAI_ENDPOINT",
        env_fallbacks.get("OCI_GENAI_ENDPOINT", DEFAULT_ENDPOINT_TEMPLATE.format(region=region)),
    )
    compartment_id = _lookup_parser_value(
        parser,
        selected,
        "OCI_COMPARTMENT_OCID",
        env_fallbacks.get("OCI_COMPARTMENT_OCID", ""),
    )

    return ConfigSummary(
        path=config_path,
        profiles=profiles,
        selected_profile=selected,
        region=region or DEFAULT_REGION,
        endpoint=endpoint or DEFAULT_ENDPOINT_TEMPLATE.format(region=DEFAULT_REGION),
        default_compartment_id=compartment_id,
        has_config=has_config,
    )


def build_client(config_path: str, profile: str, endpoint: str) -> GenerativeAiInferenceClient:
    try:
        config = oci.config.from_file(file_location=config_path, profile_name=profile)
    except (ConfigFileNotFound, InvalidConfig) as exc:
        raise AppConfigError(str(exc)) from exc
    return GenerativeAiInferenceClient(config=config, service_endpoint=endpoint)


def to_data_url(raw_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def pdf_to_images(raw_bytes: bytes, max_pages: int, dpi: int) -> list[dict[str, Any]]:
    document = fitz.open(stream=raw_bytes, filetype="pdf")
    try:
        page_payloads: list[dict[str, Any]] = []
        scale = dpi / 72
        matrix = fitz.Matrix(scale, scale)
        for page_index in range(min(max_pages, document.page_count)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_bytes = pixmap.tobytes("png")
            page_payloads.append(
                {
                    "page_number": page_index + 1,
                    "mime_type": "image/png",
                    "raw_bytes": image_bytes,
                    "data_url": to_data_url(image_bytes, "image/png"),
                }
            )
        return page_payloads
    finally:
        document.close()


def image_to_payload(raw_bytes: bytes, filename: str, mime_type: str | None) -> list[dict[str, Any]]:
    detected_mime = mime_type or mimetypes.guess_type(filename)[0] or "image/png"
    return [
        {
            "page_number": 1,
            "mime_type": detected_mime,
            "raw_bytes": raw_bytes,
            "data_url": to_data_url(raw_bytes, detected_mime),
        }
    ]


def normalize_upload(raw_bytes: bytes, filename: str, mime_type: str | None, max_pdf_pages: int, pdf_dpi: int) -> list[dict[str, Any]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or mime_type == "application/pdf":
        return pdf_to_images(raw_bytes, max_pages=max_pdf_pages, dpi=pdf_dpi)
    return image_to_payload(raw_bytes, filename, mime_type)


def build_generic_request(prompt: str, images: list[dict[str, Any]], max_output_tokens: int, temperature: float) -> GenericChatRequest:
    content: list[Any] = [TextContent(text=prompt)]
    for image in images:
        content.append(
            ImageContent(
                image_url=ImageUrl(
                    url=image["data_url"],
                    detail="HIGH",
                )
            )
        )

    return GenericChatRequest(
        api_format=GenericChatRequest.API_FORMAT_GENERIC,
        messages=[
            SystemMessage(content=[TextContent(text=SYSTEM_PROMPT)]),
            UserMessage(content=content),
        ],
        temperature=temperature,
        max_tokens=max_output_tokens,
    )


def build_cohere_request(prompt: str, images: list[dict[str, Any]], max_output_tokens: int, temperature: float) -> CohereChatRequestV2:
    content: list[Any] = [CohereTextContentV2(text=prompt)]
    for image in images:
        content.append(
            CohereImageContentV2(
                image_url=CohereImageUrlV2(
                    url=image["data_url"],
                    detail="HIGH",
                )
            )
        )

    return CohereChatRequestV2(
        api_format=CohereChatRequestV2.API_FORMAT_COHEREV2,
        messages=[
            CohereSystemMessageV2(content=[CohereTextContentV2(text=SYSTEM_PROMPT)]),
            CohereUserMessageV2(content=content),
        ],
        temperature=temperature,
        max_tokens=max_output_tokens,
    )


def extract_text_from_chat_response(chat_response: Any) -> str:
    if hasattr(chat_response, "message") and getattr(chat_response, "message"):
        message = chat_response.message
        content = getattr(message, "content", None) or []
        texts = [item.text for item in content if hasattr(item, "text") and getattr(item, "text", None)]
        return "\n".join(texts).strip()

    if hasattr(chat_response, "choices") and getattr(chat_response, "choices"):
        choice = chat_response.choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) or []
        texts = [item.text for item in content if hasattr(item, "text") and getattr(item, "text", None)]
        return "\n".join(texts).strip()

    return ""


def parse_json_payload(text: str) -> tuple[Any | None, str | None]:
    stripped = text.strip()
    if not stripped:
        return None, "Model returned an empty response."

    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()

    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as exc:
        object_start = stripped.find("{")
        object_end = stripped.rfind("}")
        if object_start != -1 and object_end > object_start:
            candidate = stripped[object_start : object_end + 1]
            try:
                return json.loads(candidate), None
            except json.JSONDecodeError:
                try:
                    repaired_candidate = repair_json(candidate, return_objects=True)
                    return repaired_candidate, "JSON was auto-repaired from the model response."
                except Exception:
                    pass
        try:
            repaired = repair_json(stripped, return_objects=True)
            return repaired, "JSON was auto-repaired from the model response."
        except Exception:
            pass
        return None, f"JSON parsing failed: {exc}"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def flatten_json_leaves(value: Any, prefix: str = "") -> dict[str, str]:
    leaves: dict[str, str] = {}

    if isinstance(value, dict):
        if not value:
            leaves[prefix or "$"] = "{}"
            return leaves
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            leaves.update(flatten_json_leaves(child, child_prefix))
        return leaves

    if isinstance(value, list):
        if not value:
            leaves[prefix or "$"] = "[]"
            return leaves
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            leaves.update(flatten_json_leaves(child, child_prefix))
        return leaves

    if value is None:
        leaves[prefix or "$"] = ""
    elif isinstance(value, (str, int, float, bool)):
        leaves[prefix or "$"] = str(value)
    else:
        leaves[prefix or "$"] = json.dumps(value, sort_keys=True)
    return leaves


def extract_result_text(result: dict[str, Any]) -> str:
    parsed_json = result.get("parsed_json")
    if parsed_json is not None:
        leaves = flatten_json_leaves(parsed_json)
        return "\n".join(item for item in leaves.values() if item.strip())
    return str(result.get("raw_text") or "")


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def score_result(
    result: dict[str, Any],
    *,
    expected_text: str = "",
    expected_json: Any | None = None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "text_similarity_pct": None,
        "json_path_coverage_pct": None,
        "json_value_similarity_pct": None,
        "missing_json_fields": None,
        "extra_json_fields": None,
        "overall_score_pct": None,
    }
    weighted_scores: list[float] = []
    weights: list[float] = []

    if expected_text.strip():
        actual_text = extract_result_text(result)
        text_similarity = round(_ratio(expected_text, actual_text) * 100, 2)
        metrics["text_similarity_pct"] = text_similarity
        weighted_scores.append(text_similarity)
        weights.append(0.45)

    if expected_json is not None:
        expected_leaves = flatten_json_leaves(expected_json)
        actual_parsed_json = result.get("parsed_json")
        actual_leaves = flatten_json_leaves(actual_parsed_json) if actual_parsed_json is not None else {}

        expected_paths = set(expected_leaves.keys())
        actual_paths = set(actual_leaves.keys())
        common_paths = sorted(expected_paths & actual_paths)

        path_coverage = round((len(common_paths) / len(expected_paths) * 100), 2) if expected_paths else 100.0
        if common_paths:
            value_similarity = round(
                sum(_ratio(expected_leaves[path], actual_leaves[path]) for path in common_paths) / len(common_paths) * 100,
                2,
            )
        else:
            value_similarity = 0.0

        missing_fields = len(expected_paths - actual_paths)
        extra_fields = len(actual_paths - expected_paths)

        metrics["json_path_coverage_pct"] = path_coverage
        metrics["json_value_similarity_pct"] = value_similarity
        metrics["missing_json_fields"] = missing_fields
        metrics["extra_json_fields"] = extra_fields

        json_component = (path_coverage * 0.6) + (value_similarity * 0.4)
        weighted_scores.append(json_component)
        weights.append(0.55 if expected_text.strip() else 1.0)

    if weighted_scores:
        total_weight = sum(weights) or 1.0
        overall = sum(score * (weight / total_weight) for score, weight in zip(weighted_scores, weights))
        metrics["overall_score_pct"] = round(overall, 2)

    return metrics


def _maybe_float(value: str) -> float | None:
    candidate = (value or "").strip()
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", candidate):
        try:
            return float(candidate)
        except ValueError:
            return None
    return None


def _extract_number_tokens(value: str) -> list[str]:
    return re.findall(r"[-+]?\d+(?:\.\d+)?", value or "")


def compare_model_jsons(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    parsed_models = {
        model_label: flatten_json_leaves(result["parsed_json"])
        for model_label, result in results.items()
        if result.get("parsed_json") is not None
    }
    model_labels = list(results.keys())
    summary_by_model = {
        model_label: {
            "model": model_label,
            "parsed_json": model_label in parsed_models,
            "missing_field_count": 0,
            "value_mismatch_count": 0,
            "numeric_mismatch_count": 0,
            "number_token_mismatch_count": 0,
            "word_count_mismatch_count": 0,
        }
        for model_label in model_labels
    }
    if len(parsed_models) < 2:
        return {
            "available": False,
            "reason": "At least two models need valid parsed JSON before cross-model diffing is meaningful.",
            "model_summary": list(summary_by_model.values()),
            "disagreements": [],
            "conclusion": "",
        }

    all_paths = sorted({path for leaves in parsed_models.values() for path in leaves.keys()})
    disagreements: list[dict[str, Any]] = []

    for path in all_paths:
        present = {model_label: parsed_models[model_label][path] for model_label in parsed_models if path in parsed_models[model_label]}
        missing_models = [model_label for model_label in model_labels if model_label not in present]

        normalized_values: dict[str, str] = {model_label: normalize_text(value) for model_label, value in present.items()}
        counts: dict[str, int] = {}
        for normalized in normalized_values.values():
            counts[normalized] = counts.get(normalized, 0) + 1
        consensus_normalized = max(counts.items(), key=lambda item: (item[1], item[0]))[0] if counts else ""
        consensus_models = sorted([model_label for model_label, value in normalized_values.items() if value == consensus_normalized])
        representative_model = consensus_models[0] if consensus_models else (next(iter(present)) if present else "")
        consensus_value = present.get(representative_model, "")

        issue_types: list[str] = []
        if missing_models:
            issue_types.append("missing_field")
            for model_label in missing_models:
                summary_by_model[model_label]["missing_field_count"] += 1

        numeric_values = {model_label: _maybe_float(value) for model_label, value in present.items()}
        if present and all(value is not None for value in numeric_values.values()) and len({value for value in numeric_values.values() if value is not None}) > 1:
            issue_types.append("numeric_mismatch")
            for model_label, numeric_value in numeric_values.items():
                if numeric_value != _maybe_float(consensus_value):
                    summary_by_model[model_label]["numeric_mismatch_count"] += 1
                    summary_by_model[model_label]["value_mismatch_count"] += 1
        else:
            number_tokens = {model_label: _extract_number_tokens(value) for model_label, value in present.items()}
            if len({tuple(tokens) for tokens in number_tokens.values()}) > 1:
                issue_types.append("number_token_mismatch")
                consensus_numbers = _extract_number_tokens(consensus_value)
                for model_label, tokens in number_tokens.items():
                    if tokens != consensus_numbers:
                        summary_by_model[model_label]["number_token_mismatch_count"] += 1
                        summary_by_model[model_label]["value_mismatch_count"] += 1
            elif len({value for value in normalized_values.values()}) > 1:
                word_counts = {
                    model_label: len([token for token in re.split(r"\s+", (value or "").strip()) if token])
                    for model_label, value in present.items()
                }
                if len(set(word_counts.values())) > 1:
                    issue_types.append("word_count_mismatch")
                    consensus_word_count = word_counts.get(representative_model)
                    for model_label, word_count in word_counts.items():
                        if word_count != consensus_word_count:
                            summary_by_model[model_label]["word_count_mismatch_count"] += 1
                            summary_by_model[model_label]["value_mismatch_count"] += 1
                else:
                    issue_types.append("value_mismatch")
                    for model_label, normalized in normalized_values.items():
                        if normalized != consensus_normalized:
                            summary_by_model[model_label]["value_mismatch_count"] += 1

        if issue_types:
            disagreements.append(
                {
                    "path": path,
                    "issue_types": ", ".join(issue_types),
                    "missing_models": ", ".join(missing_models) if missing_models else "",
                    "consensus_models": ", ".join(consensus_models),
                    "consensus_value": consensus_value[:300],
                    "values_by_model": {model_label: value for model_label, value in present.items()},
                }
            )

    model_summary = list(summary_by_model.values())
    ranked_models = sorted(
        model_summary,
        key=lambda item: (
            item["missing_field_count"],
            item["value_mismatch_count"],
            item["numeric_mismatch_count"],
            item["number_token_mismatch_count"],
            item["word_count_mismatch_count"],
        ),
    )
    best_model = ranked_models[0]["model"] if ranked_models else ""
    conclusion = (
        f"{best_model} looks most consistent with the cross-model consensus."
        if best_model
        else ""
    )
    return {
        "available": True,
        "reason": "",
        "model_summary": model_summary,
        "disagreements": disagreements,
        "conclusion": conclusion,
    }


def run_extraction(
    *,
    config_path: str,
    profile: str,
    compartment_id: str,
    endpoint: str,
    model_id: str,
    api_mode: str,
    uploaded_name: str,
    uploaded_mime_type: str | None,
    uploaded_bytes: bytes,
    max_pdf_pages: int,
    pdf_dpi: int,
    user_prompt: str,
    max_output_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    if not compartment_id.strip():
        raise AppConfigError("A compartment OCID is required to call OCI Generative AI.")

    normalized_images = normalize_upload(
        uploaded_bytes,
        filename=uploaded_name,
        mime_type=uploaded_mime_type,
        max_pdf_pages=max_pdf_pages,
        pdf_dpi=pdf_dpi,
    )
    client = build_client(config_path=config_path, profile=profile, endpoint=endpoint)

    if api_mode == "cohere_v2":
        request = build_cohere_request(
            prompt=user_prompt,
            images=normalized_images,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    else:
        request = build_generic_request(
            prompt=user_prompt,
            images=normalized_images,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

    started = time.perf_counter()
    try:
        response = client.chat(
            ChatDetails(
                serving_mode=OnDemandServingMode(model_id=model_id),
                compartment_id=compartment_id,
                chat_request=request,
            )
        )
    except ServiceError as exc:
        message = getattr(exc, "message", str(exc))
        raise RuntimeError(f"OCI service error ({exc.status}): {message}") from exc

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response_dict = oci.util.to_dict(response.data)
    raw_text = extract_text_from_chat_response(response.data.chat_response)
    parsed_json, parse_error = parse_json_payload(raw_text)

    return {
        "request": {
            "model_id": model_id,
            "api_mode": api_mode,
            "endpoint": endpoint,
            "compartment_id": compartment_id,
            "input_file": uploaded_name,
            "input_mime_type": uploaded_mime_type or "",
            "rendered_pages": len(normalized_images),
            "rendered_page_numbers": [item["page_number"] for item in normalized_images],
            "pdf_dpi": pdf_dpi if uploaded_name.lower().endswith(".pdf") else None,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        },
        "timing": {
            "elapsed_ms": elapsed_ms,
        },
        "parsed_json": parsed_json,
        "parse_error": parse_error,
        "raw_text": raw_text,
        "raw_response": response_dict,
        "preview_images": [
            {
                "page_number": item["page_number"],
                "mime_type": item["mime_type"],
                "data_url": item["data_url"],
            }
            for item in normalized_images
        ],
    }
