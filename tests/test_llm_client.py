
"""Unit tests for the Ollama LLM client."""

from unittest.mock import Mock

import pytest

from app.agent.llm_client import ask_llm


def test_llm_returns_answer() -> None:
    """The client returns the model response."""

    fake_client = Mock()
    fake_client.chat.return_value.message.content = (
        "The ETL schema is invalid."
    )

    result = ask_llm(
        "Explain schema validation errors",
        client=fake_client,
    )

    assert result == "The ETL schema is invalid."
    fake_client.chat.assert_called_once()

    kwargs = fake_client.chat.call_args.kwargs
    assert kwargs["model"] == "qwen3:1.7b"
    assert kwargs["think"] is False


def test_empty_prompt_is_rejected() -> None:
    """Empty prompts must be rejected."""

    with pytest.raises(ValueError):
        ask_llm("   ")


def test_empty_llm_response_is_rejected() -> None:
    """Empty model responses are not accepted."""

    fake_client = Mock()
    fake_client.chat.return_value.message.content = ""

    with pytest.raises(RuntimeError):
        ask_llm(
            "Diagnose an ETL incident",
            client=fake_client,
        )
