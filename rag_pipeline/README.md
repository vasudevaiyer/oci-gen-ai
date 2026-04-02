# OCI Multi-Format RAG Pipeline

Self-contained RAG backend for `pdf`, `docx`, `ppt/pptx`, `xls/xlsx`, `txt`, `json`, `rst`, and image files with Oracle Database vector search, OCI Generative AI, structure-aware chunking, image extraction, and document-management APIs.

## Deployment Paths

- Local or VM-first runtime from this repo for direct development and testing
- OCI Resource Manager stack for provisioning the full OCI foundation and bootstrapping the application on a private VM

The Resource Manager stack lives in:

- [`rag_pipeline_stack`](../rag_pipeline_stack)
- operator guide in [`RESOURCE_MANAGER_STACK.md`](RESOURCE_MANAGER_STACK.md)

Use that stack when you want OCI to provision:

- VCN, subnets, NSGs, and gateways
- private Autonomous AI Database
- private application VM
- public jump host
- public API Gateway
- generated Vault secret for the application schema password

The current stack design keeps the application source separate from the Resource Manager zip:

- RM zip = Terraform stack bundle
- `app_source_url` = Git or archive location that the VM pulls during bootstrap

For Resource Manager, upload the sanitized stack bundle and provide the application source URL and ref in the stack variables form.

## Resource Manager Quick Start

1. Create or open a stack in OCI Resource Manager with the bundle from `rag_pipeline_stack`.
2. Let Resource Manager auto-populate `tenancy_ocid`, `compartment_ocid`, and `region`.
3. Provide `home_region`, Vault and key, existing ADB admin password secret, image OCID, SSH public key, and application source values.
4. Run `Plan`, then `Apply`.
5. After apply, use the outputs for the public UI/API URL and the generated application schema secret.

The stack includes `schema.yaml`, so the Resource Manager variable form is grouped and OCI-aware.

## Features

- Structure-aware parsing and chunking across supported formats instead of one generic chunking path
- GenAI-assisted document understanding for multimodal interpretation, image captioning, and richer chunk metadata
- File-type-specific chunking strategies for PDF, DOCX, PPTX, XLSX, RST, plain text, JSON, and image inputs
- `Cohere Embed 4.0` for dense embeddings
- `Command A` for grounded answer generation
- `Vision` for image captioning, image-file parsing, and multimodal answer context
- Arabic-aware normalization with the numeric reversal fix ported locally
- GenAI-assisted query understanding with retrieval-oriented rewrites and intent-aware ranking
- Image search through image embeddings plus image-caption retrieval
- Image filtering during ingest to suppress repeated tiny/header-footer-style assets before indexing
- Governance surface for upload, import, inventory, reindex, and delete operations
- Simplified chat-first workspace for grounded end-user questions
- Session-scoped workspace transcript with recent-query navigation in the UI
- Expandable supporting sources panel so evidence stays available without crowding the answer view
- Sticky ask box with answers rendered above the composer for easier back-and-forth review
- Oracle Database tables created locally under the `RP_` namespace

## Runtime assumptions

- Python environment: `/u01/venv`
- Wallet directory: `/home/opc/wallet`
- OCI config: `/home/opc/.oci/config`

## Setup

1. Copy `.env.example` to `.env` and fill in Oracle and OCI values.
2. Install dependencies in `/u01/venv` if needed.
3. Start the API:

```bash
./rag_service.sh
```

The service listens on port `8045`.

To restart it in the background and keep it running after logout:

```bash
./restart_service.sh
```

Runtime files:

- PID: `.runtime/rag_service.pid`
- Log: `.runtime/rag_service.log`

## Web UI

Open the solution-pack UI at `http://<host>:8045/`.

It provides two focused surfaces:

- `/` workspace: compact chat-first UI for grounded Q&A with answer transcript, expandable evidence, recent queries, and visual matches
- `/governance`: document upload, folder import, inventory, inspect, reindex, and delete actions in a separate admin-facing surface


## Supported parsers and chunking

| File type | Parser | Structure detected | Chunking strategy |
| --- | --- | --- | --- |
| `pdf` | `PdfParser` | hierarchical paged sections | `pdf_section_window` |
| `docx` | `DocxParser` | hierarchical sections | `generic_blocks` |
| `ppt` / `pptx` | `PptxParser` | slides | `slide_window` |
| `xls` / `xlsx` | `XlsxParser` | workbook sheets, tables, key-value regions | `xlsx_sheet_window` |
| `rst` | `RstParser` | rst sections | `rst_section_window` |
| `txt` | `TextParser` | line sections | `generic_blocks` |
| `json` | `JsonParser` | structured records / blocks | `generic_blocks` |
| image files (`png`, `jpg`, `jpeg`, `webp`, `gif`, `bmp`, `tif`, `tiff`) | `ImageFileParser` | image analysis blocks from vision parsing | `generic_blocks` |

`generic_blocks` is the fallback strategy for formats where block-level structure is already emitted by the parser.

## How GenAI is used

- Document understanding: vision and chat models assist multimodal interpretation during ingestion, including image-file parsing, extracted-image captioning, and richer document metadata for retrieval.
- Query understanding: the retrieval layer uses GenAI to classify query intent and generate retrieval-oriented rewrites before vector search and reranking.
- Grounded answering: chat generation is performed only after retrieval, using matched text chunks and optional image context as evidence.

## Workspace behavior

- The end-user workspace is chat-first and keeps the current browser session transcript in session storage.
- Recent Queries in the right rail let users jump back to earlier answers from the same session.
- Supporting Sources are collapsed by default and can be expanded per answer.
- Visual Support shows image thumbnails only; full image and caption/source details appear on click.
- The current chat memory is UI-session memory, not backend conversational state.

## Main API endpoints

- `POST /api/bootstrap`
- `GET /api/status`
- `POST /api/documents/upload`
- `POST /api/documents/import-folder`
- `GET /api/documents`
- `GET /api/documents/{document_id}`
- `DELETE /api/documents/{document_id}`
- `POST /api/documents/{document_id}/reindex`
- `POST /api/reindex`
- `POST /api/search`
- `POST /api/chat`

## Upload and folder management

### Upload files

Use multipart upload against `/api/documents/upload` with one or more files.

### Import an existing folder

```json
{
  "folder_path": "/path/to/files",
  "recurse": true,
  "ingest": true
}
```

## Search and chat

### Search

```json
{
  "query": "find the DR readiness checklist",
  "top_k": 6,
  "file_types": ["pdf", "rst"],
  "include_images": true
}
```

Search remains available by API for retrieval testing and integration use cases.

### Chat

```json
{
  "question": "Summarize the workbook sections related to revenue trends",
  "top_k": 6,
  "file_types": ["xlsx"],
  "include_images": true
}
```

## Notes

- The wallet stays external and is not copied into the repo.
- Image captions are generated during ingest for extracted document images and image-file uploads.
- The workspace UI no longer loads the full document inventory on page load; inventory management is intentionally isolated to the governance page.
- Supporting sources in the workspace are intentionally collapsible to keep the main answer area cleaner during demos and end-user use.
- Document metadata now captures parser and chunking hints such as `document_structure`, `chunking_strategy`, `parser_used`, and image filtering summaries.
