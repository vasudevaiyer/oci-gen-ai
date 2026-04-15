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
        self.config = oci.config.from_file(str(settings.oci_config_path), settings.oci_profile)
        self.client = GenerativeAiInferenceClient(
            config=self.config,
            service_endpoint=settings.oci_endpoint,
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
        for data_url in data_urls:
            response = self.client.embed_text(
                EmbedTextDetails(
                    serving_mode=OnDemandServingMode(model_id=self.settings.embedding_model_id),
                    compartment_id=self.settings.oci_compartment_id,
                    inputs=[data_url],
                    input_type="IMAGE",
                    output_dimensions=self.settings.embedding_dimensions,
                    embedding_types=["float"],
                )
            )
            vectors.append(response.data.embeddings_by_type["float"][0])
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
                                        "You answer questions over an Arabic policy document. "
                                        "Use only the provided context. If the context is insufficient, say so clearly. "
                                        "Preserve numbers, percentages, and numeric limits exactly as written in the context. "
                                        "Answer in Arabic when the user asks in Arabic. Cite source labels like [S1], [S2] inline."
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
