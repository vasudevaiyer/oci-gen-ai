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


def build_client() -> tuple[OpenAI, str]:
    client = OpenAI(
        api_key=get_setting("OCI_GENAI_API_KEY"),
        base_url=get_setting("OCI_GENAI_BASE_URL"),
        project=get_setting("OCI_GENAI_PROJECT_OCID"),
    )
    model = get_setting("OCI_GENAI_MODEL")
    return client, model


st.set_page_config(page_title="OCI Enterprise AI Chat", layout="centered")
st.title("OCI Enterprise AI Chat")
st.caption("Simple Streamlit chat app backed by OCI Enterprise AI through the Responses API.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi, I am connected to your OCI Enterprise AI project. Ask me anything to test the setup.",
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Type your message")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        client, model = build_client()
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = client.responses.create(
                    model=model,
                    input=[
                        {"role": msg["role"], "content": [{"type": "input_text", "text": msg["content"]}]}
                        for msg in st.session_state.messages
                    ],
                )
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
    if st.button("Clear chat"):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Chat cleared. Ask a new question when you're ready.",
            }
        ]
        st.rerun()
