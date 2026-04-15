# AgentStudio Arabic RAG Demo

This repository contains a small retrieval-augmented generation application for asking Arabic questions over a PDF policy document. It combines:

- A FastAPI backend for ingestion, retrieval, and chat
- Oracle AI Database vector storage for chunk embeddings
- OCI Generative AI for embeddings and answer generation
- A React/Vite frontend optimized for Arabic and RTL interaction

The current parser is tailored to Arabic policy PDFs and the sample corpus in `data/`.

## What The Application Does

The app ingests PDF files from `data/`, extracts Arabic text, splits the content into overlapping chunks, generates embeddings through OCI Generative AI, stores those vectors in Oracle AI Database, and answers user questions using retrieved passages from the indexed corpus.

The UI lets users:

- Trigger a full index rebuild
- Ask Arabic questions about the document
- View source excerpts used for each answer
- Click suggested follow-up questions
- Toggle light and dark themes
- Clear or reset the chat session

## Architecture

### Backend

The backend lives in `backend/app`:

- `main.py`: FastAPI app, REST API, CORS, static file serving, SPA fallback
- `config.py`: environment-driven settings and defaults
- `pdf_parser.py`: Arabic PDF parsing, article/chapter detection, chunk generation
- `ingestion.py`: rebuild workflow orchestration and in-memory ingest status
- `db.py`: Oracle AI Database schema creation, rebuild, and similarity search
- `oci_services.py`: OCI Generative AI embedding and chat calls
- `schemas.py`: Pydantic response/request models and internal dataclasses

### Frontend

The frontend lives in `frontend`:

- React 18 + Vite
- Arabic/RTL chat interface
- Calls `/api/status`, `/api/ingest`, and `/api/chat`
- Proxies `/api` and `/corpus-assets` to the backend in dev mode
- Serves the production build from `frontend/dist` through FastAPI in packaged mode

## Repository Layout

```text
.
├── backend/app/
├── data/
│   └── IA_Arabic_Policy.pdf
├── frontend/
│   ├── src/
│   └── dist/
├── logs/
├── rag.env.example
├── rag.env
└── rag_service.sh
```

## Requirements

You need:

- Python 3.10+
- Node.js 18+ and npm
- Access to an Oracle AI Database / ATP instance with vector support
- An OCI config file with credentials and access to OCI Generative AI
- An Oracle wallet for the target database

This repo does not currently include a Python dependency manifest. The backend environment needs packages equivalent to:

- `fastapi`
- `uvicorn`
- `python-dotenv`
- `oracledb`
- `oci`
- `pydantic`
- `pypdf` or `PyPDF2`

Example install:

```bash
/u01/venv/bin/pip install fastapi uvicorn python-dotenv oracledb oci pydantic pypdf
```

## Configuration

Copy the sample environment file and fill in your values:

```bash
cp rag.env.example rag.env
```

Required variables:

```env
ORACLE_USER=
ORACLE_PASSWORD=
ORACLE_DSN=genaivasuatp_high
ORACLE_WALLET_DIR=/home/opc/wallet
ORACLE_WALLET_PASSWORD=
OCI_CONFIG_PATH=/home/opc/.oci/config
OCI_PROFILE=DEFAULT
OCI_COMPARTMENT_OCID=
```

Useful optional overrides:

- `APP_NAME` default: `AgentStudio`
- `DATA_DIR` default: `./data`
- `CHUNK_TABLE_NAME` default: `rag_arabic_chunks`
- `IMAGE_TABLE_NAME` default: `rag_arabic_images`
- `EMBEDDING_DIMENSIONS` default: `1024`
- `MAX_CHUNK_WORDS` default: `180`
- `CHUNK_OVERLAP_WORDS` default: `28`
- `MAX_CONTEXT_CHUNKS` default: `6`
- `MAX_CONTEXT_IMAGES` default: `3`
- `OCI_GENAI_ENDPOINT` default: OCI Chicago inference endpoint
- `OCI_EMBED_MODEL_ID` default: `cohere.embed-v4.0`
- `OCI_CHAT_MODEL_ID` default: `cohere.command-a-03-2025`
- `OCI_VISION_MODEL_ID` default: `cohere.command-a-vision`
- `RAG_HOST` default: `0.0.0.0`
- `RAG_PORT` default: `8020`
- `RAG_PYTHON_BIN` default: `/u01/venv/bin/python`

Important environment note:

- `rag_service.sh` loads `rag.env`, or `.env` as a fallback, before starting `uvicorn`.
- The Python app itself auto-loads only `.env`.
- If you run the backend directly and want to use `rag.env`, source it first with `set -a; source rag.env; set +a`.

## Quick Start

### Packaged app with the service script

Build the frontend once if you want FastAPI to serve the UI:

```bash
cd frontend
npm install
npm run build
cd ..
```

Start the app:

```bash
./rag_service.sh start
./rag_service.sh status
```

Then open:

```text
http://<host>:8020
```

unless you override `RAG_PORT`.

Useful service commands:

```bash
./rag_service.sh start
./rag_service.sh stop
./rag_service.sh restart
./rag_service.sh status
```

Notes:

- The script starts `uvicorn backend.app.main:app`.
- Logs are written to `logs/rag_service.log`.
- If `frontend/dist/index.html` is missing, the API still starts but the packaged UI is not served.

### Backend and frontend separately for development

Start the backend on port `8000` so it matches the current Vite proxy:

```bash
set -a
source rag.env
set +a
/u01/venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5173
```

Important: `frontend/vite.config.js` proxies traffic to `http://127.0.0.1:8000`, while `rag_service.sh` defaults to port `8020`. If you change either port, update the other side as needed.

## Ingestion Flow

The `/api/ingest` endpoint currently supports only a full rebuild.

During rebuild the backend:

1. Scans `DATA_DIR` recursively for `*.pdf`
2. Extracts text with `pypdf` or `PyPDF2`
3. Detects Arabic chapter and article boundaries
4. Normalizes common RTL PDF number-ordering issues before chunking
5. Splits content into overlapping text windows
6. Generates embeddings with OCI Generative AI
7. Creates Oracle vector tables if needed
8. Rebuilds the chunk table and reloads the corpus

### Arabic numeral handling during chunking

Arabic PDF extraction can reverse short numeric tokens when text is read from RTL layouts. The parser normalizes a few common patterns before building chunks so retrieved text and answers keep the intended values.

Examples:

- `.03` is normalized to `30.`
- `٪05` is normalized to `50٪`
- dotted list markers such as `.10` and `.41` are normalized to `10.` and `14.`

This logic lives in the bidi-number normalization step in the PDF parser and is aimed at common policy-document extraction artifacts rather than full Arabic number conversion.

The parser is currently focused on text chunks. Image extraction is scaffolded in the schema and API, but this implementation returns no image matches during ingestion or chat.

## API Endpoints

### `GET /api/health`

Returns:

```json
{"status":"ok"}
```

### `GET /api/status`

Returns corpus counts, ingestion state, active model IDs, and the last rebuild stats.

Example shape:

```json
{
  "chunks": 0,
  "images": 0,
  "documents": 0,
  "ingest_running": false,
  "models": {
    "embedding": "cohere.embed-v4.0",
    "chat": "cohere.command-a-03-2025"
  },
  "stats": {}
}
```

### `POST /api/ingest`

Request:

```json
{"rebuild": true}
```

Possible response statuses:

- `started`
- `running`
- `ignored`

### `POST /api/chat`

Request:

```json
{
  "question": "ما أهداف العمل عن بعد؟",
  "top_k": 6
}
```

Response includes:

- `answer`
- `sources`
- `matched_images`
- `follow_up_questions`
- `model`

If the index is empty, the API returns HTTP `400` with:

```json
{"detail":"Index is empty. Run ingestion first."}
```

## Frontend Behavior

The React UI:

- Polls `/api/status` every 5 seconds
- Shows corpus counts and active model IDs
- Lets the user rebuild the index from the sidebar
- Displays chat answers with source cards
- Shows suggested follow-up questions returned by the backend
- Sets `lang="ar"` and `dir="rtl"` at runtime

## Corpus Expectations

By default the application reads PDF files from:

```text
data/
```

The sample corpus included here is:

- `data/IA_Arabic_Policy.pdf`

If you want to use a different corpus, place additional PDFs under `data/` or override `DATA_DIR`.

Source paths returned by the API are relative to `DATA_DIR`, and the backend exposes that directory under `/corpus-assets`.

## Troubleshooting

- `Missing required environment variables`: create `rag.env` from `rag.env.example` and populate all required Oracle and OCI values before running `rag_service.sh`.
- `Frontend build not found`: run `npm install && npm run build` inside `frontend` if you want FastAPI to serve the UI on port `8020`.
- `Index is empty. Run ingestion first.`: start the app, trigger `POST /api/ingest`, and wait for `/api/status` to report non-zero `chunks`.
- Vite can reach the UI but chat fails: make sure the backend is running on port `8000` in dev mode, or update `frontend/vite.config.js`.
- Oracle wallet or OCI auth errors: verify `ORACLE_WALLET_DIR`, `ORACLE_WALLET_PASSWORD`, `OCI_CONFIG_PATH`, `OCI_PROFILE`, and `OCI_COMPARTMENT_OCID`.

## Current Limitations

- No Python dependency file is included yet.
- Ingestion supports only full rebuild, not incremental updates.
- Image retrieval structures exist in the API, but image indexing is not populated in the current pipeline.
- CORS is currently wide open (`allow_origins=["*"]`), which is acceptable for a demo but not for production hardening.
