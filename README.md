# OCI GenAI Solutions

This repository groups multiple OCI Generative AI demos and solution patterns under one roof.

## Included solutions

- `function_tool_demo/`: OCI Agent function-calling demo with a local weather tool and static JSON-backed responses.
- `multi_modal_extract/`: Streamlit app for comparing OCI-hosted multimodal GenAI models on PDF and image extraction, with original file preview, rendered page preview, parsed JSON, and extracted field views.
- `rag_pipeline/`: multi-format RAG ingestion and retrieval pipeline with structure-aware parsing, GenAI-assisted understanding, governance UI, and chat-first workspace.
- `rag_pipeline_stack/`: OCI Resource Manager Terraform stack for provisioning the private VM, Autonomous AI Database, networking, Vault secret, jump host, and public API Gateway used by `rag_pipeline`.

## Notes

- `rag_pipeline` intentionally excludes local-only runtime artifacts, generated extracted images, and UI mockup preview files.
- `rag_pipeline_stack` keeps Terraform state and environment-specific tfvars out of Git by default.
- Each solution folder keeps its own README with setup and usage details.
