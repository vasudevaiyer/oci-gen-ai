from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .db import OracleVectorStore
from .services.cohere_service import OciGenAiService


class RetrievalService:
    def __init__(self, settings: Settings, store: OracleVectorStore, genai: OciGenAiService) -> None:
        self.settings = settings
        self.store = store
        self.genai = genai
        self._query_profile_cache: dict[str, dict[str, Any]] = {}
        self._intent_cache: dict[str, set[str]] = {}
        self._rerank_cache: dict[str, list[str]] = {}

    def search(self, query: str, *, top_k: int, file_types: list[str] | None = None, include_images: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        profile = self._query_profile(query)
        search_queries = self._search_queries(query, profile=profile)
        chunk_candidates = self._collect_chunk_candidates(search_queries, top_k=top_k, file_types=file_types)
        image_candidates: list[dict[str, Any]] = []
        if include_images:
            image_candidates = self._collect_image_candidates(search_queries, top_k=top_k, file_types=file_types)
            chunk_candidates = self._augment_chunk_candidates_from_images(query, chunk_candidates, image_candidates)
        chunk_matches = self._hybrid_rank(query, chunk_candidates, top_k)
        image_matches: list[dict[str, Any]] = []
        if include_images:
            image_candidates = self._candidate_images_for_query(query, chunk_matches, image_candidates)
            image_matches = self._rerank_images(query, image_candidates, min(self.settings.max_context_images, top_k))
        return chunk_matches, image_matches

    def answer(self, question: str, *, top_k: int, file_types: list[str] | None = None, include_images: bool = True, image_data_url: str | None = None) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
        chunk_matches, image_matches = self.search(question, top_k=top_k, file_types=file_types, include_images=include_images)
        multimodal_matches = image_matches
        if image_data_url:
            query_image_embedding = self.genai.embed_image_data_urls([image_data_url])[0]
            multimodal_matches = self.store.query_images(query_image_embedding, self.settings.max_context_images, file_types=file_types)
        prompt = self._build_prompt(question, chunk_matches, multimodal_matches)
        answer, model_id = self.genai.answer_with_command_a(prompt)
        self.store.log_query(
            question,
            {"top_k": top_k, "file_types": file_types or [], "include_images": include_images},
            {
                "chunks": len(chunk_matches),
                "images": len(multimodal_matches),
                "generation_model": model_id,
                "embedding_model": self.settings.embedding_model_id,
                "vision_model": self.settings.vision_model_id,
            },
        )
        return answer, model_id, chunk_matches, multimodal_matches

    def _query_profile(self, question: str) -> dict[str, Any]:
        cached = self._query_profile_cache.get(question)
        if cached is not None:
            return cached

        profile: dict[str, Any] | None = None
        understander = getattr(self.genai, "understand_query_for_retrieval", None)
        if callable(understander):
            try:
                profile = understander(question, limit=3)
            except Exception:
                profile = None

        if profile is None:
            profile = {}
            classifier = getattr(self.genai, "classify_query_intents", None)
            if callable(classifier):
                try:
                    profile["intents"] = list(classifier(question))
                except Exception:
                    profile["intents"] = []
            expander = getattr(self.genai, "expand_query_for_retrieval", None)
            if callable(expander):
                try:
                    profile["rewrites"] = expander(question)
                except Exception:
                    profile["rewrites"] = []

        normalized = _normalize_query_profile(profile, question)
        self._query_profile_cache[question] = normalized
        self._intent_cache[question] = set(normalized["intents"])
        return normalized

    def _search_queries(self, query: str, *, profile: dict[str, Any] | None = None) -> list[str]:
        active_profile = profile or self._query_profile(query)
        queries = [query]
        for rewrite in active_profile.get("rewrites", []):
            if rewrite and rewrite not in queries:
                queries.append(rewrite)
        return queries

    def _collect_chunk_candidates(self, queries: list[str], *, top_k: int, file_types: list[str] | None) -> list[dict[str, Any]]:
        collected: dict[str, dict[str, Any]] = {}
        per_query_k = max(top_k * 4, 12)
        for search_query in queries:
            query_embedding = self.genai.embed_texts([search_query], input_type="SEARCH_QUERY")[0]
            for match in self.store.query_chunks(query_embedding, per_query_k, file_types=file_types):
                existing = collected.get(match["chunk_id"])
                if existing is None:
                    collected[match["chunk_id"]] = {**match, "matched_queries": [search_query]}
                    continue
                if search_query not in existing["matched_queries"]:
                    existing["matched_queries"].append(search_query)
                if match["score"] > existing["score"]:
                    collected[match["chunk_id"]] = {**match, "matched_queries": existing["matched_queries"]}
        return list(collected.values())

    def _collect_image_candidates(self, queries: list[str], *, top_k: int, file_types: list[str] | None) -> list[dict[str, Any]]:
        collected: dict[str, dict[str, Any]] = {}
        per_query_k = min(self.settings.max_context_images * 2, top_k * 2)
        for search_query in queries:
            query_embedding = self.genai.embed_texts([search_query], input_type="SEARCH_QUERY")[0]
            for match in self.store.query_images(query_embedding, per_query_k, file_types=file_types):
                existing = collected.get(match["image_id"])
                if existing is None:
                    collected[match["image_id"]] = {**match, "matched_queries": [search_query]}
                    continue
                if search_query not in existing["matched_queries"]:
                    existing["matched_queries"].append(search_query)
                if match["score"] > existing["score"]:
                    collected[match["image_id"]] = {**match, "matched_queries": existing["matched_queries"]}
        return list(collected.values())


    def _augment_chunk_candidates_from_images(
        self,
        question: str,
        chunk_candidates: list[dict[str, Any]],
        image_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not image_candidates:
            return chunk_candidates

        chunk_map = {match["chunk_id"]: {**match} for match in chunk_candidates}
        related_ids: list[str] = []
        question_variants = [question]

        for image in image_candidates:
            related_chunk_id = image.get("related_chunk_id")
            if not related_chunk_id:
                continue
            caption_score = _caption_match_score(question_variants, image)
            support_score = min(0.24, (image["score"] * 0.16) + (caption_score * 0.22))
            if support_score <= 0.07:
                continue
            if related_chunk_id not in chunk_map:
                related_ids.append(related_chunk_id)
            existing = chunk_map.get(related_chunk_id)
            if existing is not None:
                existing["image_caption_support"] = max(float(existing.get("image_caption_support", 0.0)), support_score)

        if related_ids:
            for chunk in self.store.get_chunks_by_ids(sorted(set(related_ids))):
                chunk_map[chunk["chunk_id"]] = {
                    **chunk,
                    "matched_queries": [question],
                    "image_caption_support": 0.0,
                }

        for image in image_candidates:
            related_chunk_id = image.get("related_chunk_id")
            if not related_chunk_id or related_chunk_id not in chunk_map:
                continue
            caption_score = _caption_match_score(question_variants, image)
            support_score = min(0.24, (image["score"] * 0.16) + (caption_score * 0.22))
            if support_score <= 0.07:
                continue
            chunk_map[related_chunk_id]["image_caption_support"] = max(
                float(chunk_map[related_chunk_id].get("image_caption_support", 0.0)),
                support_score,
            )

        return list(chunk_map.values())

    def _hybrid_rank(self, question: str, matches: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        profile = self._query_profile(question)
        ai_rank_bonus = self._ai_rank_bonus(question, matches, limit=max(top_k, min(len(matches), 8)), profile=profile)
        reranked = []
        for match in matches:
            query_variants = [question, *(match.get("matched_queries") or [])]
            haystack_tokens = _query_tokens(
                f"{match['title']} {' '.join(match['section_path'])} {match['content']} {match['source_path']}"
            )
            lexical_score = max((len(_query_tokens(variant) & haystack_tokens) / max(len(_query_tokens(variant)), 1)) for variant in query_variants)
            section_tokens = _query_tokens(f"{match['title']} {' '.join(match['section_path'])}")
            section_score = max((len(_query_tokens(variant) & section_tokens) / max(len(_query_tokens(variant)), 1)) for variant in query_variants)
            image_bonus = 0.03 if match.get("image_refs") else 0.0
            caption_support_bonus = float(match.get("image_caption_support", 0.0))
            matched_query_bonus = min(0.04, 0.015 * max(len(match.get("matched_queries") or []) - 1, 0))
            structure_bonus = _structural_bonus(match, profile)
            answer_shape_bonus = _answer_shape_bonus(match, profile)
            generic_penalty = _generic_heading_penalty(match)
            combined = (
                (match["score"] * 0.58)
                + (lexical_score * 0.12)
                + (section_score * 0.05)
                + image_bonus
                + matched_query_bonus
                + structure_bonus
                + answer_shape_bonus
                + caption_support_bonus
                + ai_rank_bonus.get(match["chunk_id"], 0.0)
                - generic_penalty
            )
            reranked.append({**match, "score": combined})
        reranked.sort(key=lambda item: item["score"], reverse=True)
        consolidated = self._consolidate_section_matches(reranked)
        return consolidated[:top_k]

    def _consolidate_section_matches(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        consolidated: list[dict[str, Any]] = []
        seen_sections: dict[tuple[str, tuple[str, ...]], int] = {}
        for match in matches:
            key = _section_key(match)
            if key is None:
                consolidated.append(match)
                continue
            existing_index = seen_sections.get(key)
            if existing_index is None:
                seen_sections[key] = len(consolidated)
                consolidated.append(match)
                continue
            existing = consolidated[existing_index]
            if _match_richness(match) > _match_richness(existing):
                merged = {**match, "score": max(match["score"], existing["score"])}
                consolidated[existing_index] = merged
            else:
                consolidated[existing_index] = {**existing, "score": max(existing["score"], match["score"])}
        consolidated.sort(key=lambda item: item["score"], reverse=True)
        return consolidated

    def _rerank_images(self, question: str, matches: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        intents = self._query_intents(question)
        reranked = []
        for match in matches:
            query_variants = [question, *(match.get("matched_queries") or [])]
            haystack_tokens = _query_tokens(f"{match['caption_text']} {' '.join(match['section_path'])} {match['source_path']}")
            lexical_score = max((len(_query_tokens(variant) & haystack_tokens) / max(len(_query_tokens(variant)), 1)) for variant in query_variants)
            visual_bonus = 0.08 if "visual" in intents else 0.0
            combined = (match["score"] * 0.76) + (lexical_score * 0.16) + visual_bonus
            reranked.append({**match, "score": combined})
        reranked.sort(key=lambda item: item["score"], reverse=True)
        return reranked[:top_k]

    def _candidate_images_for_query(self, question: str, chunk_matches: list[dict[str, Any]], image_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not chunk_matches:
            return []

        intents = self._query_intents(question)
        top_chunks = chunk_matches[: max(1, min(len(chunk_matches), 4))]
        top_chunk_ids = {match["chunk_id"] for match in top_chunks}
        top_document_ids = {match["document_id"] for match in top_chunks}
        top_source_paths = {match["source_path"] for match in top_chunks}
        referenced_images = {ref for match in top_chunks for ref in (match.get("image_refs") or [])}

        fallback_images = self._fallback_images_from_chunks(top_chunks)

        if not image_matches:
            return fallback_images

        directly_linked: list[dict[str, Any]] = []
        same_document: list[dict[str, Any]] = []
        for image in image_matches:
            image_path = image.get("image_path")
            related_chunk_id = image.get("related_chunk_id")
            image_document_id = image.get("document_id")
            image_source_path = image.get("source_path")
            if related_chunk_id in top_chunk_ids or image_path in referenced_images:
                directly_linked.append(image)
                continue
            if image_document_id in top_document_ids or image_source_path in top_source_paths:
                same_document.append(image)

        if directly_linked:
            return directly_linked
        if "visual" in intents:
            return same_document or image_matches or fallback_images
        return fallback_images

    def _fallback_images_from_chunks(self, chunk_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fallback_images: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for match in chunk_matches:
            for index, image_path in enumerate(match.get("image_refs") or []):
                normalized_path = str(image_path or "").strip()
                if not normalized_path or normalized_path in seen_paths:
                    continue
                seen_paths.add(normalized_path)
                fallback_images.append(
                    {
                        "image_id": f"ref::{normalized_path}",
                        "document_id": match["document_id"],
                        "related_chunk_id": match["chunk_id"],
                        "image_path": normalized_path,
                        "caption_text": match["title"] or "Relevant visual context",
                        "source_path": match["source_path"],
                        "section_path": match["section_path"],
                        "score": max(float(match.get("score", 0.0)) - (index * 0.01), 0.0),
                    }
                )
        return fallback_images

    def _query_intents(self, question: str) -> set[str]:
        cached = self._intent_cache.get(question)
        if cached is not None:
            return cached
        profile = self._query_profile(question)
        intents = set(profile["intents"])
        self._intent_cache[question] = intents
        return intents

    def _ai_rank_bonus(self, question: str, matches: list[dict[str, Any]], *, limit: int, profile: dict[str, Any]) -> dict[str, float]:
        if not matches:
            return {}

        cache_key = self._candidate_cache_key(question, matches, limit, profile)
        cached = self._rerank_cache.get(cache_key)
        if cached is None:
            reranker = getattr(self.genai, "rerank_retrieval_candidates", None)
            candidate_payload = [
                {
                    "chunk_id": match["chunk_id"],
                    "title": match["title"],
                    "section_path": " > ".join(match["section_path"]),
                    "source_path": match["source_path"],
                    "chunk_type": match.get("chunk_type", ""),
                    "excerpt": (match.get("content") or "")[:420],
                }
                for match in sorted(matches, key=lambda item: item["score"], reverse=True)[: max(limit * 2, 8)]
            ]
            ranked_ids: list[str] = []
            if callable(reranker):
                try:
                    rerank_prompt = _rerank_question(question, profile)
                    ranked_ids = [
                        candidate_id
                        for candidate_id in reranker(rerank_prompt, candidate_payload, limit=min(len(candidate_payload), limit))
                        if candidate_id in {candidate["chunk_id"] for candidate in candidate_payload}
                    ]
                except Exception:
                    ranked_ids = []
            self._rerank_cache[cache_key] = ranked_ids
            cached = ranked_ids

        if not cached:
            return {}

        total = max(len(cached), 1)
        return {chunk_id: 0.18 * (total - index) / total for index, chunk_id in enumerate(cached)}

    def _candidate_cache_key(self, question: str, matches: list[dict[str, Any]], limit: int, profile: dict[str, Any]) -> str:
        ordered = sorted(matches, key=lambda item: item["score"], reverse=True)[: max(limit * 2, 8)]
        signature = ",".join(f"{match['chunk_id']}:{match['score']:.6f}" for match in ordered)
        profile_signature = "|".join(
            [
                ",".join(profile.get("intents", [])),
                str(profile.get("answer_shape", "")),
                ",".join(profile.get("evidence_types", [])),
            ]
        )
        return f"{question}::{limit}::{profile_signature}::{signature}"

    def _build_prompt(self, question: str, chunk_matches: list[dict[str, Any]], image_matches: list[dict[str, Any]]) -> str:
        context_blocks = [
            f"[S{index}] {match['title']} | {' > '.join(match['section_path'])} | {match['source_path']}\n{match['content']}"
            for index, match in enumerate(chunk_matches, start=1)
        ]
        image_blocks = [
            f"[I{index}] {image['source_path']} | {' > '.join(image['section_path'])} | {image['image_path']}\n{image['caption_text']}"
            for index, image in enumerate(image_matches, start=1)
        ]
        context_text = "\n\n".join(context_blocks) if context_blocks else "No matching text context."
        image_text = "\n\n".join(image_blocks) if image_blocks else "None"
        return (
            "User question:\n"
            f"{question}\n\n"
            "Retrieved context:\n"
            f"{context_text}\n\n"
            "Relevant images:\n"
            f"{image_text}\n\n"
            "Answer in the same language as the user when possible. Cite source labels inline when used."
        )


def _normalize_query_profile(profile: dict[str, Any], question: str) -> dict[str, Any]:
    intents = sorted(
        {
            str(intent).strip().casefold()
            for intent in profile.get("intents", [])
            if str(intent).strip().casefold() in {"procedural", "regulatory", "visual", "reference", "technical"}
        }
    )
    answer_shape = str(profile.get("answer_shape") or "").strip().casefold()
    if answer_shape not in {"steps", "rule", "limit", "definition", "parameter_list", "comparison", "summary"}:
        answer_shape = _default_answer_shape(intents, question)
    evidence_types = sorted(
        {
            str(value).strip().casefold()
            for value in profile.get("evidence_types", [])
            if str(value).strip().casefold() in {"section", "procedure", "policy", "table", "list", "figure", "configuration"}
        }
    )
    rewrites = []
    seen = {question.casefold()}
    for value in profile.get("rewrites", []):
        cleaned = str(value).strip()
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        rewrites.append(cleaned)
    return {
        "intents": intents,
        "answer_shape": answer_shape,
        "evidence_types": evidence_types,
        "rewrites": rewrites[:3],
    }


def _default_answer_shape(intents: list[str], question: str) -> str:
    lowered = question.casefold()
    if "procedural" in intents:
        return "steps"
    if "reference" in intents and any(token in lowered for token in ("compare", "difference", "versus", "vs")):
        return "comparison"
    if "reference" in intents:
        return "parameter_list"
    if "regulatory" in intents and any(token in lowered for token in ("how many", "how much", "limit", "maximum")):
        return "limit"
    if "regulatory" in intents:
        return "rule"
    if "technical" in intents and any(token in lowered for token in ("what is", "define", "meaning")):
        return "definition"
    return "summary"


def _rerank_question(question: str, profile: dict[str, Any]) -> str:
    parts = [f"Question: {question}"]
    if profile.get("intents"):
        parts.append("Intents: " + ", ".join(profile["intents"]))
    if profile.get("answer_shape"):
        parts.append("Expected answer shape: " + profile["answer_shape"])
    if profile.get("evidence_types"):
        parts.append("Preferred evidence: " + ", ".join(profile["evidence_types"]))
    return "\n".join(parts)


def _section_key(match: dict[str, Any]) -> tuple[str, tuple[str, ...]] | None:
    source_path = str(match.get("source_path") or "").strip()
    section_path = match.get("section_path") or []
    if not source_path or not section_path:
        return None
    normalized = tuple(_normalize_section_label(part) for part in section_path if str(part).strip())
    if not normalized:
        return None
    return source_path, normalized


def _normalize_section_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def _match_richness(match: dict[str, Any]) -> tuple[int, int, int]:
    content = str(match.get("content") or "")
    image_refs = match.get("image_refs") or []
    return (len(content), len(content.split()), len(image_refs))


def _query_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"\w+", text.casefold()) if len(token) >= 2}


def _structural_bonus(match: dict[str, Any], profile: dict[str, Any]) -> float:
    answer_shape = profile.get("answer_shape", "")
    evidence_types = set(profile.get("evidence_types", []))
    chunk_type = str(match.get("chunk_type") or "").casefold()
    title = str(match.get("title") or "")
    content = str(match.get("content") or "")

    bonus = 0.0
    if answer_shape == "steps" or "procedure" in evidence_types:
        if "procedure" in chunk_type or _step_density(content) >= 0.18:
            bonus += 0.08
    if answer_shape in {"parameter_list", "comparison"} or evidence_types.intersection({"table", "configuration", "list"}):
        if "table" in chunk_type or _reference_density(content) >= 0.2:
            bonus += 0.08
    if answer_shape in {"rule", "limit"} or "policy" in evidence_types:
        if "policy" in chunk_type or "clause" in chunk_type or _list_density(content) >= 0.18:
            bonus += 0.06
    if answer_shape == "definition" and _definition_density(title, content) >= 0.18:
        bonus += 0.05
    if "figure" in evidence_types and ((match.get("image_refs") or []) or "figure" in chunk_type):
        bonus += 0.04
    return min(bonus, 0.18)


def _answer_shape_bonus(match: dict[str, Any], profile: dict[str, Any]) -> float:
    answer_shape = profile.get("answer_shape", "")
    content = str(match.get("content") or "")
    if answer_shape == "steps":
        return min(0.07, _step_density(content) * 0.22)
    if answer_shape == "parameter_list":
        return min(0.08, _reference_density(content) * 0.24)
    if answer_shape == "comparison":
        return min(0.07, (_reference_density(content) + _list_density(content)) * 0.16)
    if answer_shape == "limit":
        return min(0.07, (_numeric_density(content) + _list_density(content)) * 0.14)
    if answer_shape == "rule":
        return min(0.06, _list_density(content) * 0.16)
    if answer_shape == "definition":
        return min(0.05, _definition_density(str(match.get("title") or ""), content) * 0.18)
    return 0.0


def _generic_heading_penalty(match: dict[str, Any]) -> float:
    title = str(match.get("title") or "").strip().casefold()
    content = str(match.get("content") or "")
    if re.fullmatch(r"page\s+\d+", title):
        return 0.06
    if len(title.split()) <= 3 and len(content.splitlines()) <= 2:
        return 0.03
    return 0.0


def _step_density(text: str) -> float:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    step_lines = sum(1 for line in lines if re.match(r"^(?:step\s+\d+|\d+[.)]|[A-Za-z]\)|[-*•])", line, flags=re.IGNORECASE))
    return step_lines / len(lines)


def _reference_density(text: str) -> float:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    reference_lines = sum(1 for line in lines if any(marker in line for marker in (":", "=", "|", "<", ">", "(")))
    return reference_lines / len(lines)


def _list_density(text: str) -> float:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    list_lines = sum(1 for line in lines if re.match(r"^(?:\d+[.)]|[A-Za-z]\)|[-*•])", line))
    return list_lines / len(lines)


def _numeric_density(text: str) -> float:
    tokens = re.findall(r"\S+", text)
    if not tokens:
        return 0.0
    numeric_tokens = sum(1 for token in tokens if re.search(r"\d", token) or "%" in token)
    return numeric_tokens / len(tokens)


def _definition_density(title: str, text: str) -> float:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    lead = lines[0]
    score = 0.0
    if len(title.split()) <= 8:
        score += 0.1
    if ":" in lead or len(lead.split()) <= 12:
        score += 0.1
    if len(lines) <= 6:
        score += 0.08
    return score


def _caption_match_score(query_variants: list[str], image: dict[str, Any]) -> float:
    haystack_tokens = _query_tokens(
        f"{image.get('caption_text', '')} {' '.join(image.get('section_path') or [])} {image.get('source_path', '')}"
    )
    if not haystack_tokens:
        return 0.0
    return max(
        (len(_query_tokens(variant) & haystack_tokens) / max(len(_query_tokens(variant)), 1))
        for variant in query_variants
    )
