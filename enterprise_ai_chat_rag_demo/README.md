# OCI Enterprise AI Chat and RAG Demo

This folder contains a clean, publishable demo of two API-key-based OCI Enterprise AI applications:

- `app.py`
  A simple chat application using the OCI OpenAI-compatible Responses API.
- `rag_app.py`
  A grounded chat application that adds `file_search` over an OCI vector store.

This folder is intentionally limited to the working chat and RAG demos. It does not include the in-progress NL2SQL or hosted-application material.

## Deployment Model

This demo uses the self-managed pattern:

- you run the Streamlit app
- OCI hosts the model, project, vector store, and connector resources

## Architecture

### `app.py`

`Streamlit -> OCI Responses API -> model`

### `rag_app.py`

`Streamlit -> OCI Responses API -> file_search -> vector store -> synced files`

## Prerequisites

You need:

- an OCI region that supports Generative AI
- access to a target OCI compartment
- permissions to use or manage OCI Generative AI resources
- Python 3.11 or later recommended

## Recommended IAM Policies

For a simple demo, broad compartment-scoped access is the fastest path:

```text
allow group <your-group-name> to manage generative-ai-family in compartment <your-compartment-name>
```

For connectors that read from Object Storage, you also need Object Storage read access for the connector principal:

```text
allow any-user to read object-family in compartment <your-compartment-name>
where ALL{request.principal.type='generativeaivectorconnector'}
```

## Step 1: Create an OCI Generative AI Project

Console path:

- `Analytics & AI`
- `AI Services`
- `Generative AI`
- `Projects`
- `Create project`

After creation, copy the project OCID.

## Step 2: Create an OCI Generative AI API Key

Console path:

- `Analytics & AI`
- `AI Services`
- `Generative AI`
- `API keys`
- `Create API key`

After creation, copy one secret value and store it securely.

## Step 3: Choose the Inference Endpoint and Model

Use the OCI OpenAI-compatible base URL format:

```bash
https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1
```

Example:

```bash
OCI_GENAI_BASE_URL=https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1
```

Pick a supported model for your region:

```bash
OCI_GENAI_MODEL=<supported_model_name>
```

## Step 4: Create a Vector Store for `rag_app.py`

If you only want `app.py`, you can skip this step.

Console path:

- `Analytics & AI`
- `AI Services`
- `Generative AI`
- `Vector stores`
- `Create vector store`

After creation, copy the vector store identifier.

## Step 5: Create a Data Sync Connector

Create a connector that reads files from OCI Object Storage and syncs them into the vector store.

Suggested flow:

- create or select an Object Storage bucket
- upload a few demo documents
- create a data sync connector
- point it to the bucket or prefix
- target the vector store you created

After creation, copy the connector identifier if you want it displayed in the app sidebar.

## Step 6: Run a Sync

From the connector details page:

- start a sync
- wait for ingestion to complete
- verify at least one file is indexed

## Step 7: Create `.env`

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required values:

```bash
OCI_GENAI_API_KEY=<api_key_secret>
OCI_GENAI_PROJECT_OCID=<project_ocid>
OCI_GENAI_BASE_URL=https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1
OCI_GENAI_MODEL=<supported_model_name>
```

Additional values for `rag_app.py`:

```bash
OCI_GENAI_VECTOR_STORE_ID=<vector_store_id>
OCI_GENAI_VECTOR_CONNECTOR_OCID=<vector_store_connector_ocid>
OCI_GENAI_SYSTEM_PROMPT=You are an enterprise assistant. Use the connected knowledge base whenever it is relevant.
```

## Step 8: Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Step 9: Run `app.py`

```bash
source .venv/bin/activate
streamlit run app.py
```

Good first prompts:

- `Summarize OCI Enterprise AI in 5 bullets.`
- `Explain the difference between API-key auth and OCI IAM auth.`

## Step 10: Run `rag_app.py`

```bash
source .venv/bin/activate
streamlit run rag_app.py
```

Good first prompts:

- `Summarize the uploaded document.`
- `What are the key points in the knowledge base?`

## Troubleshooting

### `Missing required setting`

One of the expected `.env` variables is missing.

### `Not Found`

Usually means one of:

- wrong region
- wrong project identifier
- wrong vector store ID
- invalid or stale API key

### `rag_app.py` gives generic answers

Usually means:

- the vector store is empty
- the sync has not completed
- the uploaded files do not contain relevant content

## Files

- `app.py`
- `rag_app.py`
- `.env.example`
- `requirements.txt`
