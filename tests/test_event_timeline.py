"""Integration tests for the agent's privacy-safe event timeline."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.agent import observability
from app.agent.orchestrator import run_agent


def _response(content="", calls=None):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=calls or [],
        )
    )


def _tool_call(name, arguments):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        )
    )


def _trace_file(tmp_path, monkeypatch):
    path = tmp_path / "agent_traces.jsonl"
    monkeypatch.setattr(observability, "TRACE_FILE", path)
    return path


def test_timeline_records_start_llm_and_completion(tmp_path, monkeypatch):
    path = _trace_file(tmp_path, monkeypatch)
    client = Mock()
    client.chat.return_value = _response("Réponse confidentielle")

    result = run_agent("Question privée", client=client)
    trace = json.loads(path.read_text(encoding="utf-8"))
    event_types = [event["event_type"] for event in trace["events"]]

    assert result["status"] == "completed"
    assert event_types == [
        "AGENT_STARTED",
        "LLM_REQUESTED",
        "LLM_RESPONDED",
        "AGENT_COMPLETED",
    ]
    assert trace["event_count"] == len(trace["events"])
    assert trace["trace_id"] == result["trace_id"]
    assert "Question privée" not in path.read_text(encoding="utf-8")
    assert "Réponse confidentielle" not in path.read_text(encoding="utf-8")


def test_timeline_records_successful_tool_call(tmp_path, monkeypatch):
    path = _trace_file(tmp_path, monkeypatch)
    client = Mock()
    client.chat.side_effect = [
        _response(calls=[
            _tool_call(
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        _response("Le pipeline est en échec."),
    ]

    result = run_agent("Analyse etl_orders_daily.", client=client)
    trace = json.loads(path.read_text(encoding="utf-8"))
    events = trace["events"]

    assert result["tool_call_count"] == 1
    assert [event["event_type"] for event in events] == [
        "AGENT_STARTED",
        "LLM_REQUESTED",
        "LLM_RESPONDED",
        "TOOL_REQUESTED",
        "TOOL_COMPLETED",
        "LLM_REQUESTED",
        "LLM_RESPONDED",
        "AGENT_COMPLETED",
    ]
    tool_event = next(
        event for event in events
        if event["event_type"] == "TOOL_COMPLETED"
    )
    assert tool_event["tool"] == "get_pipeline_status"
    assert tool_event["ok"] is True
    assert all("arguments" not in event for event in events)


def test_timeline_records_invalid_llm_failure(tmp_path, monkeypatch):
    path = _trace_file(tmp_path, monkeypatch)
    client = Mock()
    client.chat.return_value = SimpleNamespace(message=None)

    result = run_agent("Diagnose pipeline", client=client)
    trace = json.loads(path.read_text(encoding="utf-8"))

    assert result["status"] == "invalid_response"
    assert [event["event_type"] for event in trace["events"]] == [
        "AGENT_STARTED",
        "LLM_REQUESTED",
        "AGENT_FAILED",
    ]


def test_timeline_records_tool_call_limit(tmp_path, monkeypatch):
    path = _trace_file(tmp_path, monkeypatch)
    client = Mock()
    client.chat.return_value = _response(calls=[
        _tool_call(
            "get_pipeline_status",
            {"pipeline_id": "etl_orders_daily"},
        )
        for _ in range(5)
    ])

    result = run_agent("Diagnose pipeline", client=client)
    trace = json.loads(path.read_text(encoding="utf-8"))
    event_types = [event["event_type"] for event in trace["events"]]

    assert result["status"] == "limit_reached"
    assert result["tool_call_count"] == 0
    assert event_types[-2:] == ["LIMIT_REACHED", "AGENT_FAILED"]
    assert "TOOL_COMPLETED" not in event_types
