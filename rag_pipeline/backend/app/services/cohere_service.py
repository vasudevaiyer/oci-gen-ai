from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

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

from ..config import Settings


class OciGenAiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config = oci.config.from_file(str(settings.oci_config_path), settings.oci_profile)
        self.client = GenerativeAiInferenceClient(config=self.config, service_endpoint=settings.oci_endpoint)

    def embed_texts(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        if not texts:
            return []
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
        if not data_urls:
            return []
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

    def analyze_image_with_vision(self, prompt: str, *, image_data_url: str) -> tuple[str, str]:
        content = [
            CohereTextContentV2(text=prompt),
            CohereImageContentV2(
                image_url=CohereImageUrlV2(
                    url=image_data_url,
                    detail="LOW",
                )
            ),
        ]
        response = self.client.chat(
            ChatDetails(
                serving_mode=OnDemandServingMode(model_id=self.settings.vision_model_id),
                compartment_id=self.settings.oci_compartment_id,
                chat_request=CohereChatRequestV2(
                    messages=[
                        CohereSystemMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        "You analyze images and documents for retrieval. "
                                        "Focus on visible text, diagrams, tables, labels, screenshots, and document structure. "
                                        "Return concise, faithful descriptions without speculation."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(content=content),
                    ],
                    max_tokens=700,
                    temperature=0.1,
                ),
            )
        )
        return self._extract_chat_text(response), self.settings.vision_model_id

    def caption_image(self, image_path: Path, *, context_hint: str = "") -> str:
        prompt = (
            "Describe this image for retrieval in one or two concise sentences. "
            "Focus on visible text, diagram content, table labels, or UI elements. "
            f"Context hint: {context_hint or 'none'}"
        )
        answer, _ = self.analyze_image_with_vision(prompt, image_data_url=self.image_file_to_data_url(image_path))
        return answer.strip()

    def extract_image_structure(self, image_path: Path) -> dict[str, Any]:
        prompt = (
            "Analyze this image as a retrieval document. Return only valid JSON with keys: "
            "image_type, title, summary, visible_text, sections. "
            "image_type must be one of: diagram, screenshot, scanned_page, table, chart, photo, logo_only, unknown. "
            "title should be short. summary should be one or two sentences. "
            "visible_text should be a list of up to eight important visible text strings. "
            "sections should be a list of up to six objects with keys heading, block_type, content. "
            "block_type must be one of: paragraph, list_item, table, note. "
            "Focus on visible labels, text, components, layout, and relationships. JSON only."
        )
        answer, _ = self.analyze_image_with_vision(prompt, image_data_url=self.image_file_to_data_url(image_path))
        payload = self._extract_json_object(answer) or {}
        if not isinstance(payload, dict):
            payload = {}
        sections = payload.get("sections", [])
        if not isinstance(sections, list):
            sections = []
        visible_text = payload.get("visible_text", [])
        if not isinstance(visible_text, list):
            visible_text = []
        return {
            "image_type": payload.get("image_type", "unknown"),
            "title": payload.get("title", image_path.stem),
            "summary": payload.get("summary", ""),
            "visible_text": [str(item).strip() for item in visible_text[:8] if str(item).strip()],
            "sections": [item for item in sections[:6] if isinstance(item, dict)],
        }

    def understand_query_for_retrieval(self, question: str, *, limit: int = 3) -> dict[str, Any]:
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
                                        "Analyze a user question for document retrieval. "
                                        "Return only valid JSON with these keys: intents, answer_shape, evidence_types, rewrites. "
                                        "intents must be a list chosen only from: procedural, regulatory, visual, reference, technical. "
                                        "answer_shape must be one of: steps, rule, limit, definition, parameter_list, comparison, summary. "
                                        "evidence_types must be a list chosen only from: section, procedure, policy, table, list, figure, configuration. "
                                        "rewrites must be up to three short retrieval-oriented queries, each under 12 words, with cross-lingual rewrites when helpful. "
                                        "Prefer retrieval phrasing that will find the best supporting section, not conversational paraphrases."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        f"Question: {question}\n"
                                        f"Return up to {limit} rewrites.\n"
                                        "JSON only."
                                    )
                                )
                            ]
                        ),
                    ],
                    max_tokens=240,
                    temperature=0.0,
                ),
            )
        )
        text = self._extract_chat_text(response)
        payload = self._extract_json_object(text) or {}
        if not isinstance(payload, dict):
            payload = {}
        return {
            "intents": payload.get("intents", []),
            "answer_shape": payload.get("answer_shape", ""),
            "evidence_types": payload.get("evidence_types", []),
            "rewrites": payload.get("rewrites", [])[:limit],
        }

    def expand_query_for_retrieval(self, question: str, *, limit: int = 3) -> list[str]:
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
                                        "Generate short retrieval rewrites for multilingual document search. "
                                        "Return only one rewrite per line, no numbering, no commentary. "
                                        "Keep each rewrite under 12 words. Include cross-lingual rewrites when helpful. "
                                        "At least one rewrite must be a compact keyword or title-style phrase, not a full question."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        "Original query: " + question + "\n"
                                        "Produce up to " + str(limit) + " alternate search rewrites that improve retrieval over policy, procedure, visual, and multilingual content. "
                                        "Prefer precise variants, synonyms, likely section titles, and likely document phrasing. "
                                        "Include one compact title-like rewrite, for example phrases like remote work policy or travel expense policy when appropriate. "
                                        "Include one direct semantic rewrite when possible. "
                                        "If the query is in English, include Arabic when it would help match Arabic documents, especially concise title-like Arabic phrases such as سياسة العمل عن بعد when relevant. "
                                        "If the query is in Arabic, include English when it would help match English documents."
                                    )
                                )
                            ]
                        ),
                    ],
                    max_tokens=120,
                    temperature=0.1,
                ),
            )
        )
        rewrites: list[str] = []
        seen = {question.casefold()}
        for raw_line in self._extract_chat_text(response).splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip().strip('"\' ')
            if not cleaned:
                continue
            normalized = cleaned.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            rewrites.append(cleaned)
            if len(rewrites) >= limit:
                break
        return rewrites

    def classify_query_intents(self, question: str) -> set[str]:
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
                                        "Classify a user query for retrieval routing. "
                                        "Choose zero or more labels from this closed set only: procedural, regulatory, visual, reference, technical. "
                                        "Return only the labels as a comma-separated list with no explanation."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        "Query: " + question + "\n"
                                        "Use procedural for how-to steps or workflows. "
                                        "Use regulatory for policy, entitlement, allowance, rules, requirements, or approval questions. "
                                        "Use visual for diagrams, screenshots, or image-seeking questions. "
                                        "Use reference for lookup-style factual questions, fields, commands, parameters, tables, limits, or counts. "
                                        "Use technical for architecture, design, components, interfaces, or flows."
                                    )
                                )
                            ]
                        ),
                    ],
                    max_tokens=40,
                    temperature=0.0,
                ),
            )
        )
        text = self._extract_chat_text(response)
        intents: set[str] = set()
        for raw_token in re.split(r"[,\n]", text.lower()):
            cleaned = raw_token.strip()
            if cleaned in {"procedural", "regulatory", "visual", "reference", "technical"}:
                intents.add(cleaned)
        return intents

    def rerank_retrieval_candidates(self, question: str, candidates: list[dict[str, str]], *, limit: int = 6) -> list[str]:
        if not candidates or limit <= 0:
            return []

        candidate_lines = []
        for candidate in candidates:
            candidate_lines.append(
                json.dumps(
                    {
                        "chunk_id": candidate.get("chunk_id", ""),
                        "title": candidate.get("title", ""),
                        "section_path": candidate.get("section_path", ""),
                        "source_path": candidate.get("source_path", ""),
                        "chunk_type": candidate.get("chunk_type", ""),
                        "excerpt": candidate.get("excerpt", ""),
                    },
                    ensure_ascii=False,
                )
            )

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
                                        "Rank retrieved document chunks for answer relevance. "
                                        "Prefer chunks that directly answer the user's question with the most specific supporting detail. "
                                        "Favor answer-bearing clauses, limits, allowances, definitions, tables, or steps over broad introductions, cover pages, repeated headings, or nearby sections that are only topically related. "
                                        "Use only the supplied candidates. Return only chunk IDs, one per line, best first, with no commentary."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(
                            content=[
                                CohereTextContentV2(
                                    text=(
                                        f"Question: {question}\n"
                                        f"Return up to {limit} chunk IDs from this candidate set.\n"
                                        "Candidates:\n"
                                        + "\n".join(candidate_lines)
                                    )
                                )
                            ]
                        ),
                    ],
                    max_tokens=160,
                    temperature=0.0,
                ),
            )
        )

        allowed_ids = {candidate.get("chunk_id", "") for candidate in candidates}
        ranked_ids: list[str] = []
        seen: set[str] = set()
        for raw_line in self._extract_chat_text(response).splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip().strip('"\' ')
            if cleaned not in allowed_ids or cleaned in seen:
                continue
            seen.add(cleaned)
            ranked_ids.append(cleaned)
            if len(ranked_ids) >= limit:
                break
        return ranked_ids

    def answer_with_command_a(self, prompt: str) -> tuple[str, str]:
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
                                        "You answer questions over enterprise documents. "
                                        "Use only the provided context. If the context is insufficient, say so clearly. "
                                        "Cite source labels like [S1] and image labels like [I1] inline when used."
                                    )
                                )
                            ]
                        ),
                        CohereUserMessageV2(content=[CohereTextContentV2(text=prompt)]),
                    ],
                    max_tokens=1000,
                    temperature=0.2,
                ),
            )
        )
        return self._extract_chat_text(response), self.settings.chat_model_id

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
                                        "Generate concise follow-up questions for a document assistant. "
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
        text_parts = self._extract_chat_text(response)
        questions: list[str] = []
        seen: set[str] = set()
        for raw_line in text_parts.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip().strip('"\' ')
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

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        candidates = [text]
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            candidates.insert(0, match.group(0))
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _extract_chat_text(self, response) -> str:
        text_parts = []
        for item in response.data.chat_response.message.content:
            text = getattr(item, "text", None)
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()
