from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import OracleVectorStore
from .ingestion import IngestionManager
from .retrieval import RetrievalService
from .schemas import (
    BootstrapResponse,
    ChatRequest,
    ChatResponse,
    ChunkMatch,
    CorpusStatus,
    DeleteResponse,
    DocumentDetail,
    DocumentItem,
    FolderImportRequest,
    HealthResponse,
    ImageMatch,
    SearchRequest,
    SearchResponse,
    UploadResponse,
)
from .services.cohere_service import OciGenAiService


UI_DIR = Path(__file__).resolve().parent / "ui"

settings = get_settings()
store = OracleVectorStore(settings)
genai = OciGenAiService(settings)
ingestion = IngestionManager(settings, store, genai)
retrieval = RetrievalService(settings, store, genai)
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.extracted_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=settings.data_dir), name="assets")
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")


def _public_asset_url(asset_path: str) -> str:
    normalized = asset_path.lstrip("/")
    if normalized.startswith("data/"):
        normalized = normalized[len("data/") :]
    return f"/assets/{normalized}"


@app.get("/", include_in_schema=False)
def ui_home() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/governance", include_in_schema=False)
def governance_home() -> FileResponse:
    return FileResponse(UI_DIR / "governance.html")

@app.get("/mockup", include_in_schema=False)
def mockup_home() -> FileResponse:
    return FileResponse(UI_DIR / "mockup.html")

@app.get("/mockup-governance", include_in_schema=False)
def mockup_governance_home() -> FileResponse:
    return FileResponse(UI_DIR / "mockup_governance.html")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/bootstrap", response_model=BootstrapResponse)
def bootstrap() -> BootstrapResponse:
    ingestion.bootstrap()
    return BootstrapResponse(status="ok", detail="Schema and local directories initialized.")


@app.get("/api/status", response_model=CorpusStatus)
def status() -> CorpusStatus:
    counts = store.corpus_counts()
    return CorpusStatus(
        documents=counts.get("documents", 0),
        chunks=counts.get("chunks", 0),
        images=counts.get("images", 0),
        indexed_documents=counts.get("indexed_documents", 0),
        models={
            "embedding": settings.embedding_model_id,
            "chat": settings.chat_model_id,
            "vision": settings.vision_model_id,
        },
    )


@app.post("/api/documents/upload", response_model=UploadResponse)
async def upload_documents(files: list[UploadFile] = File(...)) -> UploadResponse:
    ingestion.bootstrap()
    uploaded: list[str] = []
    ingested: list[str] = []
    skipped: list[str] = []
    for file in files:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in settings.supported_extensions:
            skipped.append(file.filename)
            continue
        target = settings.uploads_dir / Path(file.filename).name
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        result = ingestion.ingest_path(target)
        uploaded.append(result.document.source_path)
        ingested.append(result.document.document_id)
    return UploadResponse(uploaded=uploaded, ingested=ingested, skipped=skipped)


@app.post("/api/documents/import-folder", response_model=UploadResponse)
def import_folder(request: FolderImportRequest) -> UploadResponse:
    folder = Path(request.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Folder path does not exist or is not a directory.")
    result = ingestion.ingest_folder(folder, recurse=request.recurse)
    return UploadResponse(**result)


@app.get("/api/documents", response_model=list[DocumentItem])
def list_documents() -> list[DocumentItem]:
    return [DocumentItem(**item) for item in store.list_documents()]


@app.get("/api/documents/{document_id}", response_model=DocumentDetail)
def document_detail(document_id: str) -> DocumentDetail:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    counts = store.document_counts(document_id)
    return DocumentDetail(document=DocumentItem(**document), chunk_count=counts["chunks"], image_count=counts["images"])


@app.delete("/api/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str) -> DeleteResponse:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    store.delete_document(document_id)
    ingestion.delete_document_assets(document["source_path"])
    image_dir = settings.extracted_images_dir / document_id
    if image_dir.exists():
        shutil.rmtree(image_dir)
    return DeleteResponse(status="deleted", deleted_document_id=document_id)


@app.post("/api/documents/{document_id}/reindex", response_model=BootstrapResponse)
def reindex_document(document_id: str, background_tasks: BackgroundTasks) -> BootstrapResponse:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    background_tasks.add_task(ingestion.ingest_path, settings.root_dir / document["source_path"])
    return BootstrapResponse(status="started", detail="Document reindex scheduled.")


@app.post("/api/reindex", response_model=BootstrapResponse)
def reindex_all(background_tasks: BackgroundTasks) -> BootstrapResponse:
    background_tasks.add_task(ingestion.rebuild_all)
    return BootstrapResponse(status="started", detail="Full reindex scheduled.")


@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    chunk_matches, image_matches = retrieval.search(
        request.query,
        top_k=request.top_k,
        file_types=request.file_types or None,
        include_images=request.include_images,
    )
    return SearchResponse(
        chunks=[
            ChunkMatch(
                chunk_id=match["chunk_id"],
                document_id=match["document_id"],
                source_path=match["source_path"],
                title=match["title"],
                section_path=" > ".join(match["section_path"]),
                excerpt=match["content"][:420],
                score=match["score"],
                chunk_type=match["chunk_type"],
                image_urls=[_public_asset_url(ref) for ref in match["image_refs"]],
            )
            for match in chunk_matches
        ],
        images=[
            ImageMatch(
                image_id=image["image_id"],
                image_url=_public_asset_url(image['image_path']),
                caption_text=image["caption_text"],
                source_path=image["source_path"],
                section_path=" > ".join(image["section_path"]),
                score=image["score"],
            )
            for image in image_matches
        ],
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    counts = store.corpus_counts()
    if counts.get("chunks", 0) == 0:
        raise HTTPException(status_code=400, detail="Index is empty. Ingest documents first.")
    answer, model_id, chunk_matches, image_matches = retrieval.answer(
        request.question,
        top_k=request.top_k,
        file_types=request.file_types or None,
        include_images=request.include_images,
        image_data_url=request.image_data_url,
    )
    return ChatResponse(
        answer=answer,
        model=model_id,
        sources=[
            ChunkMatch(
                chunk_id=match["chunk_id"],
                document_id=match["document_id"],
                source_path=match["source_path"],
                title=match["title"],
                section_path=" > ".join(match["section_path"]),
                excerpt=match["content"][:420],
                score=match["score"],
                chunk_type=match["chunk_type"],
                image_urls=[_public_asset_url(ref) for ref in match["image_refs"]],
            )
            for match in chunk_matches
        ],
        matched_images=[
            ImageMatch(
                image_id=image["image_id"],
                image_url=_public_asset_url(image['image_path']),
                caption_text=image["caption_text"],
                source_path=image["source_path"],
                section_path=" > ".join(image["section_path"]),
                score=image["score"],
            )
            for image in image_matches
        ],
    )


@app.get("/assets/{asset_path:path}")
def asset_proxy(asset_path: str):
    file_path = settings.data_dir / asset_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(file_path)
