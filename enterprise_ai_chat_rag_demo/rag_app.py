from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def get_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def get_optional_setting(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def build_client() -> tuple[OpenAI, str]:
    client = OpenAI(
        api_key=get_setting("OCI_GENAI_API_KEY"),
        base_url=get_setting("OCI_GENAI_BASE_URL"),
        project=get_setting("OCI_GENAI_PROJECT_OCID"),
    )
    model = get_setting("OCI_GENAI_MODEL")
    return client, model


def build_request_tools() -> list[dict[str, object]]:
    vector_store_id = get_setting("OCI_GENAI_VECTOR_STORE_ID")
    return [
        {
            "type": "file_search",
            "vector_store_ids": [vector_store_id],
        }
    ]


st.set_page_config(page_title="OCI Native RAG Demo", layout="centered")
st.title("OCI Native RAG Demo")
st.caption("Streamlit demo backed by OCI File Search and a native OCI vector store.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi, I can answer using your OCI vector store. Ask something grounded in your synced documents.",
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ask a document question")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        client, model = build_client()
        tools = build_request_tools()
        instructions = get_optional_setting("OCI_GENAI_SYSTEM_PROMPT")
        with st.chat_message("assistant"):
            with st.spinner("Searching documents..."):
                request_kwargs: dict[str, object] = {
                    "model": model,
                    "input": [
                        {"role": msg["role"], "content": [{"type": "input_text", "text": msg["content"]}]}
                        for msg in st.session_state.messages
                    ],
                    "tools": tools,
                }
                if instructions:
                    request_kwargs["instructions"] = instructions

                response = client.responses.create(**request_kwargs)
                answer = response.output_text.strip() or "The model returned an empty response."
                st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
    except Exception as exc:
        error_message = f"Request failed: {exc}"
        with st.chat_message("assistant"):
            st.error(error_message)
        st.session_state.messages.append({"role": "assistant", "content": error_message})

with st.sidebar:
    st.subheader("Configuration")
    st.write(f"Project: `{os.getenv('OCI_GENAI_PROJECT_OCID', 'missing')}`")
    st.write(f"Model: `{os.getenv('OCI_GENAI_MODEL', 'missing')}`")
    st.write(f"Endpoint: `{os.getenv('OCI_GENAI_BASE_URL', 'missing')}`")
    st.write(f"Vector store: `{os.getenv('OCI_GENAI_VECTOR_STORE_ID', 'missing')}`")
    st.write(f"Data connector: `{os.getenv('OCI_GENAI_VECTOR_CONNECTOR_OCID', 'not configured')}`")
    st.success("Native OCI RAG is enabled through File Search.")
    if st.button("Clear chat"):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Chat cleared. Ask another question from the knowledge base.",
            }
        ]
        st.rerun()
