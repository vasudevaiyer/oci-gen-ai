# RAG Implementation Manual

## 1. Objective

This application implements a Retrieval-Augmented Generation system for a corpus of French technical documentation stored as reStructuredText (`.rst`) files.

The corpus contains:

- technical manuals split across many files
- mathematical equations
- figures and images
- code and syntax blocks
- internal anchors and cross-references
- `toctree` hierarchies connecting related pages

The goal of the application is to:

- index the full corpus into Oracle AI Database
- retrieve the most relevant sections for a user question
- generate grounded answers using OCI Generative AI
- optionally support image-assisted questions through a multimodal path

## 2. High-Level RAG Approach

The implemented approach is:

1. Parse the `.rst` corpus into structured sections.
2. Convert sections into retrieval chunks with metadata.
3. Generate embeddings for text chunks using OCI GenAI `cohere.embed-v4.0`.
4. Store chunks and embeddings in Oracle AI Database vector tables.
5. Generate image embeddings for supported corpus images and store them in a separate vector table.
6. At query time:
   - embed the user question
   - retrieve candidate chunks from Oracle AI Database
   - apply a lightweight lexical rerank in the API
   - optionally retrieve visually similar images if the user attaches an image
   - build a grounded prompt
   - generate the final answer using OCI GenAI `cohere.command-a-03-2025`
   - if an image is attached, use `cohere.command-a-vision`

This is a practical hybrid design:

- semantic retrieval via vector similarity
- light lexical reranking in application code
- grounded generation over retrieved evidence

## 3. Why This Approach Was Chosen

This corpus is not a flat text collection.

Important characteristics:

- `.rst` files are interconnected manuals
- equations matter for meaning
- section titles matter for retrieval
- operator names and keywords matter exactly
- images sometimes carry technical meaning
- filenames contain encoding artifacts, while in-file headings are more reliable

Because of that, the implementation avoids naive fixed-text ingestion.

Instead, it preserves:

- section hierarchy
- local anchors
- image references
- equation labels
- code-block markers

## 4. How `.rst` Files Are Handled

### 4.1 Parsing Strategy

The parser is implemented in:

- `backend/app/rst_parser.py`

It is a lightweight structure-aware parser, not a full Docutils AST pipeline.

What it does:

- scans headings based on reStructuredText underline conventions
- builds section hierarchy from heading levels
- splits section content into paragraph-like blocks
- creates chunk windows from those blocks
- preserves section path and important RST artifacts as metadata

Why this approach was used:

- it is simpler to maintain
- it works well for this extracted corpus
- it preserves enough structure for retrieval quality
- it avoids overcomplicating the ingestion path

### 4.2 Section Detection

The parser identifies headings using underline markers such as:

- `=`
- `-`
- `~`
- `^`
- `"`

This allows the app to reconstruct a path like:

`Méthodes de sous-structuration dynamique classique > Méthode de Craig-Bampton`

That section path is included in the retrieval text and returned to the UI.

### 4.3 Chunking Strategy

Chunking is block-aware, not character-only.

Current rules:

- content is first split into paragraph blocks
- chunks are then built up to a configured word budget
- overlap is preserved between consecutive chunks

Current config defaults:

- `MAX_CHUNK_WORDS=220`
- `CHUNK_OVERLAP_WORDS=35`

Why:

- keeps local context together
- avoids breaking equations and code explanations too aggressively
- improves retrieval for technical questions

## 5. How Math Equations Are Handled

The corpus contains both:

- block math directives like `.. math::`
- inline math like `:math:\`...\``

Handling strategy:

- block math is preserved as a `[Math]` marker in cleaned chunk text
- inline math remains in the chunk text
- equation labels are extracted into metadata where present

Examples of preserved signals:

- `:math:\`E\``
- `:math:\`\nu\``
- labeled equations such as `:label: eq-r3.08.01-3.1.1-1`

Why this matters:

- users ask theory-heavy questions
- equations often define the meaning of a section
- removing all math would damage retrieval quality

Limitations:

- the app does not perform symbolic math parsing
- it does not index equations separately as formula objects
- retrieval still treats equations as part of the chunk text

## 6. How Code Blocks Are Handled

The corpus contains many syntax or command examples.

Handling strategy:

- `.. code-block::` directives are preserved as markers such as:
  - `[Code block: text]`
- surrounding explanatory prose stays in the same chunk

Why:

- many questions refer to commands, operator syntax, and procedural usage
- code blocks without surrounding explanation are often not useful
- explanation plus code together improves answer quality

Examples of useful content types:

- command syntax
- operator definitions
- examples using `DEFI_MATERIAU`, `AFFE_MATERIAU`, `DYNA_VIBRA`, etc.

## 7. How Images Are Handled

### 7.1 Text-Side Image Handling

Image references are extracted from `.rst` directives:

- `.. image::`
- `.. figure::`

They are preserved in chunk text as markers such as:

- `[Image: images/Object_1.svg]`

Image paths are also stored as metadata so the UI can display related images for retrieved chunks.

### 7.2 Image Vector Search

Supported corpus images are indexed in a separate vector table.

Current supported formats for image embedding:

- `png`
- `jpg`
- `jpeg`
- `gif`
- `webp`

Unsupported for OCI image embedding in this flow:

- `svg`

This is why:

- SVG images are still linked to the relevant text chunks
- but they are not embedded into the image vector table

### 7.3 User-Attached Images

The UI includes an `Attach Image` option.

If the user attaches an image:

1. the image is embedded with `cohere.embed-v4.0`
2. similar indexed corpus images are retrieved from Oracle AI Database
3. the answer request goes through `cohere.command-a-vision`

This supports questions like:

- "Find a similar figure in the manuals"
- "What does this technical image correspond to?"
- "Which section explains a figure like this?"

## 8. How Anchors and Cross-References Are Handled

The corpus contains explicit anchors such as:

- `.. _U4.43.01:`
- `.. _RefImage_...:`
- `.. _RefNumPara_...:`

Handling strategy:

- anchors are extracted and stored in chunk metadata
- they are also included in retrieval text
- this helps retrieval when users ask about specific labeled concepts or cross-linked content

The app does not currently build a full navigation graph of cross-reference edges, but it preserves enough anchor information to improve chunk relevance and traceability.

## 9. How `toctree` Structure Influences Retrieval

The corpus contains many `index.rst` files with `toctree` definitions.

This matters because:

- one logical manual is often split into multiple `.rst` files
- file order and hierarchy are meaningful
- retrieval benefits from knowing document grouping

The current implementation uses:

- the file hierarchy
- in-file titles
- section path

It does not yet build a full explicit `toctree` graph in the database.

That would be a reasonable future enhancement if you want manual-level navigation or document graph retrieval.

## 10. Embedding Strategy

Embeddings are handled in:

- `backend/app/oci_services.py`

### Text Embeddings

Text chunks are embedded with:

- `cohere.embed-v4.0`

Settings:

- `input_type="SEARCH_DOCUMENT"` for corpus chunks
- `input_type="SEARCH_QUERY"` for user questions
- `output_dimensions=1024`

Why:

- multilingual support is required because the corpus is in French
- technical semantics matter more than pure keyword matching
- Oracle AI Database supports vector search directly

### Image Embeddings

Supported images are embedded using the same model:

- `cohere.embed-v4.0`

with:

- `input_type="IMAGE"`

## 11. Retrieval Strategy

Retrieval is implemented across:

- `backend/app/db.py`
- `backend/app/main.py`

### 11.1 First-Stage Retrieval

The application queries Oracle AI Database with:

- `vector_distance(..., COSINE)`

This returns the nearest chunk vectors or image vectors.

### 11.2 Lightweight Hybrid Rerank

After vector recall, the API applies a simple lexical rerank.

This logic is in:

- `backend/app/main.py`

It boosts chunks where query tokens also appear in:

- title
- section path
- chunk content

Why this helps:

- technical operator names often need exact matches
- pure vector search can blur closely related operator pages
- a small lexical signal improves retrieval without adding a separate reranker service

### 11.3 Current Scope

Current retrieval is:

- vector recall in Oracle AI Database
- application-side lexical rerank

Not yet implemented:

- dedicated OCI reranker model integration
- BM25 index
- manual graph traversal

## 12. Generation Strategy

Answer generation is implemented in:

- `backend/app/oci_services.py`

### Text Answering

Model:

- `cohere.command-a-03-2025`

Used for:

- standard text questions over retrieved chunks

### Vision Answering

Model:

- `cohere.command-a-vision`

Used for:

- questions with attached user images

### Prompting

The API builds a grounded prompt containing:

- the user question
- retrieved chunk context labeled as `[S1]`, `[S2]`, etc.
- retrieved image matches labeled as `[I1]`, `[I2]`, etc.

The model is instructed to:

- answer using the provided context
- say when context is insufficient
- cite sources using source labels

## 13. Oracle AI Database Design

The vector store is implemented in:

- `backend/app/db.py`

### Tables

#### `rag_chunks`

Stores:

- source path
- document code
- title
- section path
- chunk index
- content
- retrieval text
- anchors
- image refs
- equation labels
- metadata
- vector embedding

#### `rag_images`

Stores:

- image path
- document code
- title
- caption-like text
- related source path
- related section path
- related chunk index
- metadata
- vector embedding

### Why Two Tables

Text and images serve different retrieval paths:

- chunk retrieval answers most questions
- image retrieval supports visual similarity and multimodal workflows

Keeping them separate simplifies:

- indexing
- querying
- UI presentation

## 14. Current UI Behavior

The frontend is implemented in:

- `frontend/src/App.jsx`
- `frontend/src/styles.css`

Features:

- chat-style questioning
- source cards for retrieved evidence
- related image thumbnails
- image upload for multimodal search
- dark mode toggle
- clear chat / reset conversation
- index rebuild button

The UI is intentionally designed as a more polished single-page app rather than a minimal form-only interface.

## 15. File-by-File Purpose

### Backend

#### `backend/app/__init__.py`

Marks the backend app directory as a Python package.

#### `backend/app/config.py`

Central configuration.

Purpose:

- loads runtime settings from environment variables
- defines paths for corpus, wallet, OCI config, and frontend build
- sets model IDs and chunking defaults

#### `backend/app/schemas.py`

Shared data models.

Purpose:

- defines internal chunk/image records
- defines FastAPI request and response models
- keeps API payloads explicit and typed

#### `backend/app/rst_parser.py`

Corpus parser and chunk builder.

Purpose:

- parse `.rst` files into sections
- detect headings
- create chunk windows
- capture anchors, image refs, equation labels
- produce chunk and image metadata for indexing

#### `backend/app/db.py`

Oracle AI Database integration.

Purpose:

- create vector tables
- insert chunk and image embeddings
- run vector similarity queries
- return corpus counts

#### `backend/app/oci_services.py`

OCI Generative AI integration.

Purpose:

- embed text chunks
- embed user queries
- embed supported images
- generate answers with text model
- generate answers with vision model
- convert local images to data URLs

#### `backend/app/ingestion.py`

Index rebuild orchestration.

Purpose:

- parse corpus
- generate embeddings
- filter supported images
- load all records into Oracle AI Database
- maintain ingestion state and summary stats

#### `backend/app/main.py`

FastAPI application entrypoint.

Purpose:

- expose API endpoints
- serve static corpus assets
- serve the built frontend
- implement chat flow
- apply lightweight hybrid reranking

### Frontend

#### `frontend/package.json`

Frontend dependency and script manifest.

Purpose:

- defines React and Vite dependencies
- provides `dev`, `build`, and `preview` scripts

#### `frontend/vite.config.js`

Vite configuration.

Purpose:

- runs local dev server
- proxies `/api` and `/corpus-assets` to FastAPI
- builds the frontend bundle into `dist`

#### `frontend/index.html`

Main HTML entry point for the React app.

#### `frontend/src/main.jsx`

Bootstraps the React application.

#### `frontend/src/App.jsx`

Main UI logic.

Purpose:

- fetches status
- runs ingestion
- sends chat requests
- handles image uploads
- renders source cards and image matches
- controls theme and conversation reset

#### `frontend/src/styles.css`

Application styling.

Purpose:

- defines layout and theme variables
- implements light/dark theme styles
- styles chat, sidebar, source cards, and controls

### Root / Misc

#### `.env.example`

Example environment configuration.

Purpose:

- shows which environment variables are required

#### `README.md`

Quick-start instructions.

Purpose:

- explains setup
- explains how to run backend and frontend
- summarizes the stack

#### `docs/RAG_IMPLEMENTATION_MANUAL.md`

This manual.

Purpose:

- explain design decisions
- explain the corpus handling strategy
- document the file-level architecture

## 16. Known Limitations

Current limitations include:

- no full Docutils AST parsing
- no explicit `toctree` graph indexing
- no dedicated reranker model in production path
- no OCR pipeline for raster images
- SVG images are not image-embedded
- no per-equation formula index
- no user/session persistence

These are acceptable for the current version, but good areas for enhancement.

## 17. Recommended Next Improvements

If you want to strengthen the solution further, the most valuable next steps are:

1. Replace the lightweight parser with a fuller Docutils-based structure extractor.
2. Add a proper reranking stage, ideally multilingual.
3. Add manual-level navigation using `index.rst` and `toctree`.
4. Normalize or repair filename encoding artifacts for cleaner display.
5. Add OCR or caption generation for diagrams where visual content matters.
6. Add evaluation scripts using `questions.json` plus a larger curated test set.
7. Add richer source grounding in the UI with explicit chunk labels and image references.

## 18. Summary

This repository now contains an OCI-native multimodal RAG application tailored to technical French `.rst` manuals.

Its main strengths are:

- Oracle AI Database vector storage and search
- OCI GenAI text and vision model integration
- structure-aware handling of `.rst` files
- preservation of equations, code-block markers, image refs, and section paths
- usable UI for real testing

It is not a generic chatbot over pasted text. It is a corpus-aware technical retrieval system designed for this specific documentation format.
