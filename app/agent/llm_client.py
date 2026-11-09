
"""Local Ollama client for OpsGuard AI."""

import os

from ollama import Client

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://127.0.0.1:11434",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:1.7b",
)

SYSTEM_PROMPT = """
You are OpsGuard AI, an MLOps diagnostic assistant.

Rules:
- Explain technical incidents clearly.
- Never invent metrics, logs, or tool results.
- Distinguish hypotheses from verified facts.
- Do not claim to have executed tools.
- Do not claim to have modified infrastructure.
- Answer in the language of the user.
"""


def ask_llm(
    prompt: str,
    *,
    client: Client | None = None,
) -> str:
    """Send a user message to the local Ollama model."""

    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    if client is None:
        client = Client(
            host=OLLAMA_HOST,
            timeout=180.0,
        )

    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        stream=False,
        think=False,
        options={
            "temperature": 0.0,
            "num_predict": 256,
        },
    )

    answer = (response.message.content or "").strip()

    if not answer:
        raise RuntimeError("Ollama returned an empty response")

    return answer


if __name__ == "__main__":
    question = (
        "Explique brièvement l'erreur "
        "SCHEMA_VALIDATION_ERROR dans un pipeline ETL."
    )

    print("OpsGuard AI - Local LLM Test")
    print("-" * 40)
    print(ask_llm(question))
