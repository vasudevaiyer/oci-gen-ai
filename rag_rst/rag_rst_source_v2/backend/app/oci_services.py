from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    ChatDetails,
    CohereChatRequestV2,
    CohereImageContentV2,
    CohereImageUrlV2,
    CohereSystemMessageV2,
    CohereTextContentV2,
    CohereUserMessageV2,
    EmbedTextDetails,
    OnDemandServingMode,
)

from .config import Settings


class OciGenAiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config, signer = self._build_auth()
        client_kwargs = {
            "config": self.config,
            "service_endpoint": settings.oci_endpoint,
        }
        if signer is not None:
            client_kwargs["signer"] = signer
        self.client = GenerativeAiInferenceClient(**client_kwargs)

    def _build_auth(self) -> tuple[dict, object | None]:
        mode = self.settings.oci_auth_mode
        if mode not in {"auto", "resource_principal", "api_key"}:
            raise RuntimeError(
                "Unsupported OCI_AUTH_MODE. Use one of: auto, resource_principal, api_key."
            )

        if mode in {"auto", "resource_principal"}:
            try:
                signer = oci.auth.signers.get_resource_principals_signer()
                return {"region": self._infer_region()}, signer
            except Exception as exc:
                if mode == "resource_principal":
                    raise RuntimeError(
                        "Failed to initialize OCI Resource Principals authentication."
                    ) from exc

        if mode in {"auto", "api_key"}:
            config = oci.config.from_file(
                str(self.settings.oci_config_path),
                self.settings.oci_profile,
            )
            return config, None

        raise RuntimeError("Unable to initialize OCI authentication.")

    def _infer_region(self) -> str:
        region = oci.regions.endpoint_to_region(self.settings.oci_endpoint)
        if region:
            return region
        fallback = self.settings.oci_endpoint.split(".generativeai.", 1)
        if len(fallback) == 2:
            region = fallback[1].split(".", 1)[0]
            if region:
                return region
        raise RuntimeError(
            "Could not infer OCI region from OCI_GENAI_ENDPOINT for Resource Principals auth."
        )

    def embed_texts(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = 16
        for index in range(0, len(texts), batch_size):
            batch = texts[index : index + batch_size]
            response = self.client.embed_text(
                EmbedTextDetails(
                    serving_mode=OnDemandServingMode(model_id=self.settings.embedding_model_id),
                    compartment_id=self.settings.oci_compartment_id,
                    inputs=batch,
                    input_type=input_type,
                    truncate="END",
                    output_dimensions=self.settings.embedding_dimensions,
                    embedding_types=["float"],
                )
            )
            vectors.extend(response.data.embeddings_by_type["float"])
        return vectors

    def embed_image_data_urls(self, data_urls: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = 8
        for index in range(0, len(data_urls), batch_size):
            batch = data_urls[index : index + batch_size]
            response = self.client.embed_text(
                EmbedTextDetails(
                    serving_mode=OnDemandServingMode(model_id=self.settings.embedding_model_id),
                    compartment_id=self.settings.oci_compartment_id,
                    inputs=batch,
                    input_type="IMAGE",
                    output_dimensions=self.settings.embedding_dimensions,
                    embedding_types=["float"],
                )
            )
            vectors.extend(response.data.embeddings_by_type["float"])
        return vectors

    def image_file_to_data_url(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def answer_question(self, prompt: str, *, image_data_url: str | None = None, use_vision: bool = False) -> tuple[str, str]:
        model_id = self.settings.vision_model_id if use_vision and image_data_url else self.settings.chat_model_id
        content = [CohereTextContentV2(text=prompt)]
        if use_vision and image_data_url:
            content.append(
                CohereImageContentV2(
                    image_url=CohereImageUrlV2(
                        url=image_data_url,
                        detail="LOW",
                    )
                )
            )
        response = self.client.chat(
            ChatDetails(
                serving_mode=OnDemandServingMode(model_id=model_id),
                compartment_id=self.settings.oci_compartment_id,
                chat_request=CohereChatRequestV2(
                    messages=[
                        CohereSystemMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        "You answer questions over French technical documentation. "
                                        "Use only the provided context. If the context is insufficient, say so clearly. "
                                        "Keep equations and operator names intact. "
                                        "When you write math, use Markdown-compatible LaTeX delimiters: "
                                        "single dollars for inline math and double dollars for standalone equations. "
                                        "Cite source labels like [S1], [S2] inline."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(content=content),
                    ],
                    max_tokens=900,
                    temperature=0.2,
                ),
            )
        )
        text_parts = []
        for item in response.data.chat_response.message.content:
            text = getattr(item, "text", None)
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip(), model_id

    def generate_follow_up_questions(self, prompt: str, *, limit: int = 3) -> list[str]:
        response = self.client.chat(
            ChatDetails(
                serving_mode=OnDemandServingMode(model_id=self.settings.chat_model_id),
                compartment_id=self.settings.oci_compartment_id,
                chat_request=CohereChatRequestV2(
                    messages=[
                        CohereSystemMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        "You generate concise follow-up questions for a documentation assistant. "
                                        "Return only plain follow-up questions, one per line, with no numbering or commentary."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(content=[CohereTextContentV2(text=prompt)]),
                    ],
                    max_tokens=180,
                    temperature=0.3,
                ),
            )
        )
        text_parts = []
        for item in response.data.chat_response.message.content:
            text = getattr(item, "text", None)
            if text:
                text_parts.append(text)

        questions: list[str] = []
        seen: set[str] = set()
        for raw_line in "\n".join(text_parts).splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip()
            cleaned = cleaned.strip("\"' ")
            if not cleaned:
                continue
            if not cleaned.endswith("?"):
                cleaned = f"{cleaned}?"
            normalized = cleaned.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            questions.append(cleaned)
            if len(questions) >= limit:
                break
        return questions
