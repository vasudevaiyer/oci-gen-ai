# RAG RST Source V2

`rag_rst_source_v2` is a separate application variant under:

`/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2`

It was created from the `rag_rst` app, but this version is designed to work with the customer-facing `source` corpus instead of `extract_docs_code-aster`.

## Purpose

This v2 app provides:

- a public chat UI for technical documentation search and Q&A
- a separate admin page for metrics, analytics, and rebuild operations
- staged ingestion for large `.rst` corpora
- Oracle AI Database-backed chunk and image indexes
- OCI Generative AI integration for embeddings and chat
- support for both OCI Resource Principals and API key auth

## Main differences from the base app

- Default corpus is `data/source`
- Separate DB tables are used for this variant:
  - `rsv2_chunks`
  - `rsv2_images`
  - `rsv2_chat_events`
- Public and admin experiences are separated:
  - `/` for chat
  - `/admin` for protected operations
- Admin actions require `X-Admin-Token`
- Ingestion inserts text progressively so the app becomes usable before a full rebuild finishes

## Folder structure

```text
rag_rst_source_v2/
├── backend/
│   └── app/
│       ├── config.py
│       ├── db.py
│       ├── ingestion.py
│       ├── main.py
│       ├── oci_services.py
│       ├── rst_parser.py
│       └── schemas.py
├── frontend/
│   ├── dist/
│   └── src/
│       ├── assets/
│       ├── App.jsx
│       ├── main.jsx
│       └── styles.css
├── data/
│   ├── extract_docs_code-aster -> ../../data/extract_docs_code-aster
│   └── source -> ../../data/source
├── logs/
├── README.md
├── rag.env
├── rag.env.example
└── rag_service.sh
```

## Corpus and parsing

The app reads `.rst` files from `DATA_DIR`.

- If `DATA_DIR` is not set, it uses `data/source`
- In this repo, `data/source` is a symlink to the shared corpus under `/u01/scripts/oci_samples/rag_rst/data/source`

The parser is lightweight and structure-aware. It handles:

- RST headings
- anchors
- `.. image::` and `.. figure::`
- `.. include::`
- math directives and inline math

The ingestion flow:

1. Parse the `.rst` corpus into chunks and image records
2. Embed and insert text chunks in batches
3. Validate image paths
4. Embed and insert supported image assets in batches

## OCI authentication

The app supports both methods.

Set `OCI_AUTH_MODE` to one of:

- `auto`
  tries Resource Principals first, then falls back to API key config
- `resource_principal`
  uses OCI Resource Principals only
- `api_key`
  uses `OCI_CONFIG_PATH` and `OCI_PROFILE`

Recommended setting:

```bash
export OCI_AUTH_MODE=auto
```

If you want API key mode explicitly:

```bash
export OCI_AUTH_MODE=api_key
export OCI_CONFIG_PATH=/home/opc/.oci/config
export OCI_PROFILE=DEFAULT
```

If you want Resource Principals explicitly:

```bash
export OCI_AUTH_MODE=resource_principal
```

## Environment variables

Typical runtime configuration:

```bash
source /u01/venv/bin/activate
export ORACLE_USER=<db_user>
export ORACLE_PASSWORD='<db_password>'
export ORACLE_DSN=<oracle_dsn>
export ORACLE_WALLET_DIR=<wallet_dir>
export ORACLE_WALLET_PASSWORD=<wallet_password>
export OCI_COMPARTMENT_OCID='<compartment_ocid>'
export OCI_AUTH_MODE=auto
export ADMIN_TOKEN='<admin_token>'
```

Optional overrides:

```bash
export DATA_DIR=/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/data/source
export OCI_GENAI_ENDPOINT=https://inference.generativeai.us-chicago-1.oci.oraclecloud.com
export OCI_EMBED_MODEL_ID=cohere.embed-v4.0
export OCI_CHAT_MODEL_ID=cohere.command-a-03-2025
export OCI_VISION_MODEL_ID=cohere.command-a-vision
```

You can also keep these in `rag.env`.

## Run locally

Backend:

```bash
source /u01/venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8015 --reload
```

Frontend dev server:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Build frontend for FastAPI serving:

```bash
cd frontend
npm run build
```

## Run as a service

Create `rag.env` from `rag.env.example`, fill in values, then:

```bash
bash rag_service.sh start
bash rag_service.sh status
bash rag_service.sh stop
bash rag_service.sh restart
```

Logs are written to:

`logs/rag_service.log`

## UI routes

- Public chat: `/`
- Admin page: `/admin`

Public UI shows:

- chat
- follow-up questions
- source cards
- optional image upload for multimodal questions

Admin UI shows:

- document, chunk, and image metrics
- ingestion status and phase
- analytics summary
- rebuild control
- CSV export

## Admin protection

Admin operations are protected by `ADMIN_TOKEN`.

The frontend sends it as:

`X-Admin-Token`

Protected endpoints:

- `GET /api/admin/status`
- `POST /api/admin/ingest`
- `GET /api/admin/analytics/summary`
- `GET /api/admin/analytics/export`

Public endpoint for lightweight UI status:

- `GET /api/public-status`

## API summary

- `GET /api/health`
- `GET /api/public-status`
- `POST /api/chat`
- `GET /api/admin/status`
- `POST /api/admin/ingest`
- `GET /api/admin/analytics/summary`
- `GET /api/admin/analytics/export`

## Frontend notes

The frontend is a React + Vite app.

Notable UI behavior:

- public and admin views are path-based in a single app
- formulas are rendered with `react-markdown`, `remark-math`, `rehype-katex`, and `katex`
- the home page uses the SIMVIA logo asset
- source-card labels are cleaned before display so raw `**...**` markup from corpus metadata is not shown

## Current indexing notes

- text chunks and images are stored separately
- only supported raster image formats are embedded for image search:
  - `.png`
  - `.jpg`
  - `.jpeg`
  - `.gif`
  - `.webp`
- `.svg` references may still appear in source content, but they are not embedded in the image vector index

## Useful files

- Backend entrypoint: [backend/app/main.py](/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/backend/app/main.py:1)
- OCI auth and GenAI client: [backend/app/oci_services.py](/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/backend/app/oci_services.py:1)
- Parser: [backend/app/rst_parser.py](/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/backend/app/rst_parser.py:1)
- Ingestion flow: [backend/app/ingestion.py](/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/backend/app/ingestion.py:1)
- Frontend app: [frontend/src/App.jsx](/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/frontend/src/App.jsx:1)
- Frontend styles: [frontend/src/styles.css](/u01/scripts/oci_samples/rag_rst/rag_rst_source_v2/frontend/src/styles.css:1)
