# Code Aster OCI RAG

An OCI-specific multimodal RAG application for French technical `.rst` documentation. The stack uses:

- OCI Generative AI embeddings with `cohere.embed-v4.0`
- OCI Generative AI chat with `cohere.command-a-03-2025`
- Optional image-assisted answers with `cohere.command-a-vision`
- Oracle AI Database vector columns for chunk and image search
- Oracle AI Database analytics table for chat usage reporting
- FastAPI backend
- React + Vite frontend
- KaTeX-based math rendering for formulas and equations in answers and source cards

## Layout

- `backend/app`: FastAPI API, RST parsing, OCI GenAI integration, Oracle vector store
- `frontend`: React UI
- `data/extract_docs_code-aster`: source manuals and image assets

## Configure

Use `/u01/venv` for Python and export the required environment variables:

```bash
source /u01/venv/bin/activate
export ORACLE_USER=<db_user>
export ORACLE_PASSWORD='<db_password>'
export ORACLE_DSN=<oracle_dsn>
export ORACLE_WALLET_DIR=<wallet_dir>
export ORACLE_WALLET_PASSWORD=<wallet_password>
export OCI_CONFIG_PATH=/home/opc/.oci/config
export OCI_PROFILE=DEFAULT
export OCI_COMPARTMENT_OCID='<compartment_ocid>'
```

## Corpus location for ingestion

The ingestion pipeline reads `.rst` source files from `DATA_DIR`.

- If `DATA_DIR` is set, ingestion uses that folder.
- If `DATA_DIR` is not set, the default source folder is `data/extract_docs_code-aster`.

Examples:

```bash
export DATA_DIR=/u01/scripts/oci_samples/rag_rst/data/source
```

or copy the corpus into:

```text
/u01/scripts/oci_samples/rag_rst/data/extract_docs_code-aster
```

Keep the original Sphinx-style folder structure under that directory so nested pages, relative image paths, and document relationships continue to resolve correctly during ingestion.

## Install backend dependencies

```bash
source /u01/venv/bin/activate
pip install -r requirements.txt
```

## Run backend

```bash
source /u01/venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Run frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Frontend runtime dependencies include:

- `react`
- `react-dom`
- `react-markdown`
- `remark-math`
- `rehype-katex`
- `katex`

## Build frontend for FastAPI serving

```bash
cd frontend
npm run build
```

FastAPI will serve the built app from `frontend/dist` when present.

## Run in background

Copy `rag.env.example` to `rag.env`, fill in the required values, then start the app with:

```bash
bash rag_service.sh start
```

The script runs `uvicorn` under `nohup`, stores the PID in `.rag_service.pid`, and writes logs to `logs/rag_service.log`, so the app stays available after logout.

Other commands:

```bash
bash rag_service.sh status
bash rag_service.sh stop
bash rag_service.sh restart
```

## API

- `GET /api/status`: current corpus counts and configured models
- `POST /api/ingest`: rebuilds the vector index in the background
- `POST /api/chat`: answers over the indexed corpus and accepts an optional `image_data_url`
- `GET /api/analytics/summary`: usage analytics summary for recent chat activity
- `GET /api/analytics/export`: exports chat usage events as CSV for Excel/download

## Usage analytics

The UI includes a `Usage analytics` panel in the left sidebar. It shows:

- total questions
- unique normalized questions
- questions asked with images
- average latency
- top repeated questions
- top source paths used in answers

The `Export 30d CSV` action downloads recent analytics in CSV format, which can be opened directly in Excel.

Analytics logging starts from new chat requests after this version is deployed.

## Notes

- Ingestion rebuilds both the text chunk table and the image table.
- Schema initialization now creates `rag_chunks`, `rag_images`, and `rag_chat_events`.
- Analytics schema also has a lazy fallback initializer, so the analytics table is created on first chat/analytics use even if a fresh ingestion has not been run yet.
- Image search is implemented with `cohere.embed-v4.0` image embeddings and Oracle AI Database vector similarity.
- The current parser is structure-aware but lightweight; it uses RST heading conventions, anchors, math directives, and image directives without requiring a separate conversion step.
- The frontend renders formulas with `react-markdown` + `remark-math` + `rehype-katex` + `katex`, and normalizes RST-style math markers such as `[Math]`, `:label:`, and `:math:\`...\`` for display.
