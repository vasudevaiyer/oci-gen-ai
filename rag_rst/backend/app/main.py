from __future__ import annotations

import re

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import OracleVectorStore
from .ingestion import IngestionManager
from .oci_services import OciGenAiService
from .schemas import (
    ChatRequest,
    ChatResponse,
    CorpusStatus,
    ImageMatch,
    IngestRequest,
    IngestResponse,
    SourceItem,
)


settings = get_settings()
store = OracleVectorStore(settings)
genai = OciGenAiService(settings)
ingestion = IngestionManager(settings, store, genai)
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/corpus-assets", StaticFiles(directory=settings.static_mount_dir), name="corpus-assets")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status", response_model=CorpusStatus)
def status() -> CorpusStatus:
    try:
        counts = store.corpus_counts()
    except Exception:
        counts = {"chunks": 0, "images": 0, "documents": 0}
    return CorpusStatus(
        chunks=counts.get("chunks", 0),
        images=counts.get("images", 0),
        documents=counts.get("documents", 0),
        ingest_running=ingestion.running,
        models={
            "embedding": settings.embedding_model_id,
            "chat": settings.chat_model_id,
            "vision": settings.vision_model_id,
        },
        stats=ingestion.last_stats,
    )


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    if ingestion.running:
        return IngestResponse(status="running", detail="Ingestion is already in progress.")
    if not request.rebuild:
        return IngestResponse(status="ignored", detail="Only full rebuild is implemented in this version.")
    background_tasks.add_task(ingestion.rebuild_index)
    return IngestResponse(status="started", detail="Ingestion started in the background.")


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    counts = store.corpus_counts()
    if counts.get("chunks", 0) == 0:
        raise HTTPException(status_code=400, detail="Index is empty. Run ingestion first.")

    query_embedding = genai.embed_texts([request.question], input_type="SEARCH_QUERY")[0]
    chunk_matches = _hybrid_rank(request.question, store.query_chunks(query_embedding, max(request.top_k * 4, 12)), request.top_k)
    image_matches: list[dict] = []
    if request.image_data_url:
        image_embedding = genai.embed_image_data_urls([request.image_data_url])[0]
        image_matches = store.query_images(image_embedding, settings.max_context_images)

    prompt = _build_prompt(request.question, chunk_matches, image_matches)
    answer, model_id = genai.answer_question(
        prompt,
        image_data_url=request.image_data_url,
        use_vision=bool(request.image_data_url),
    )
    try:
        follow_up_questions = genai.generate_follow_up_questions(
            _build_follow_up_prompt(request.question, answer, chunk_matches, image_matches)
        )
    except Exception:
        follow_up_questions = []
    if not follow_up_questions:
        follow_up_questions = _fallback_follow_up_questions(request.question, chunk_matches, image_matches)

    sources = [
        SourceItem(
            source_path=match["source_path"],
            title=match["title"],
            section_path=match["section_path"],
            score=match["score"],
            excerpt=_build_excerpt(match["content"]),
            image_urls=[f"/corpus-assets/{ref}" for ref in match["image_refs"]],
        )
        for match in chunk_matches
    ]
    matched_images = [
        ImageMatch(
            image_url=f"/corpus-assets/{image['image_path']}",
            caption_text=image["caption_text"][:240],
            score=image["score"],
            source_path=image["source_path"],
            section_path=image["section_path"],
        )
        for image in image_matches
    ]
    return ChatResponse(
        answer=answer,
        sources=sources,
        matched_images=matched_images,
        follow_up_questions=follow_up_questions,
        model=model_id,
    )


def _build_prompt(question: str, chunk_matches: list[dict], image_matches: list[dict]) -> str:
    context_blocks = []
    for index, match in enumerate(chunk_matches, start=1):
        context_blocks.append(
            f"[S{index}] {match['title']} | {match['section_path']} | {match['source_path']}\n{match['content']}"
        )
    context_section = "\n\n".join(context_blocks)
    image_blocks = []
    for index, image in enumerate(image_matches, start=1):
        image_blocks.append(
            f"[I{index}] {image['source_path']} | {image['section_path']} | {image['image_path']}\n{image['caption_text']}"
        )
    image_section = "\n\nImages similaires:\n" + "\n\n".join(image_blocks) if image_blocks else ""
    return (
        "Question utilisateur:\n"
        f"{question}\n\n"
        "Contexte récupéré:\n"
        f"{context_section}"
        f"{image_section}\n\n"
        "Réponds dans la langue de la question. "
        "Quand tu affiches une formule, utilise la syntaxe LaTeX compatible Markdown: "
        "$...$ pour l'inline et $$...$$ pour une équation sur sa propre ligne. "
        "Si une information vient du contexte, cite sa source avec [Sx] ou [Ix]."
    )


def _build_follow_up_prompt(question: str, answer: str, chunk_matches: list[dict], image_matches: list[dict]) -> str:
    source_lines = [
        f"- {match['title']} | {match['section_path']} | {match['source_path']}"
        for match in chunk_matches[:3]
    ]
    image_lines = [
        f"- {image['section_path']} | {image['image_path']}"
        for image in image_matches[:2]
    ]
    source_section = "\n".join(source_lines) if source_lines else "- Aucun"
    image_section = "\n".join(image_lines) if image_lines else "- Aucune"
    return (
        "Generate 3 concise follow-up questions for a documentation chat assistant.\n"
        "Keep them specific to the current topic and useful for the next user click.\n"
        "Avoid repeating the original question.\n"
        "Write the questions in the same language as the user's question.\n\n"
        f"User question:\n{question}\n\n"
        f"Assistant answer:\n{answer}\n\n"
        f"Top text sources:\n{source_section}\n\n"
        f"Top image matches:\n{image_section}"
    )


def _build_excerpt(content: str, limit: int = 900) -> str:
    cleaned = content.strip()
    if len(cleaned) <= limit:
        return cleaned

    cut = cleaned.rfind("\n\n", 0, limit)
    if cut >= int(limit * 0.6):
        excerpt = cleaned[:cut]
    else:
        cut = cleaned.rfind(" ", 0, limit)
        excerpt = cleaned[: cut if cut > 0 else limit]

    return excerpt.rstrip() + " ..."


def _fallback_follow_up_questions(question: str, chunk_matches: list[dict], image_matches: list[dict]) -> list[str]:
    follow_ups: list[str] = []
    seen: set[str] = set()
    lower_question = question.lower()

    for match in chunk_matches[:3]:
        title = match["title"].strip()
        section_path = match["section_path"].strip()
        candidates = [
            f"Can you summarize the section '{title}'?",
            f"What are the key points in '{section_path}'?",
        ]
        for candidate in candidates:
            normalized = candidate.casefold()
            if normalized in seen or candidate.lower() == lower_question:
                continue
            seen.add(normalized)
            follow_ups.append(candidate)
            if len(follow_ups) >= 3:
                return follow_ups

    if image_matches:
        candidate = "Can you explain the related figures or images for this topic?"
        if candidate.casefold() not in seen:
            follow_ups.append(candidate)

    generic_candidates = [
        "Can you give a step-by-step explanation?",
        "Which related section should I read next?",
        "What are the limitations or assumptions of this method?",
    ]
    for candidate in generic_candidates:
        normalized = candidate.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        follow_ups.append(candidate)
        if len(follow_ups) >= 3:
            break
    return follow_ups


def _hybrid_rank(question: str, matches: list[dict], top_k: int) -> list[dict]:
    tokens = {token for token in re.findall(r"\w+", question.lower()) if len(token) >= 4}
    reranked: list[dict] = []
    for match in matches:
        haystack = f"{match['title']} {match['section_path']} {match['content']}".lower()
        lexical_hits = sum(1 for token in tokens if token in haystack)
        lexical_score = lexical_hits / max(len(tokens), 1)
        combined = (match["score"] * 0.8) + (lexical_score * 0.2)
        reranked.append({**match, "score": combined})
    reranked.sort(key=lambda item: item["score"], reverse=True)
    return reranked[:top_k]


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    dist_dir = settings.frontend_dist_dir
    candidate = dist_dir / full_path
    if full_path and candidate.exists() and candidate.is_file():
        return FileResponse(candidate)
    index_file = dist_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build not found.")
