
"""Tests for read-only dashboard data ingestion."""

import json

import pytest

from app.dashboard.data import (
    filter_traces,
    load_report_summary,
    load_traces,
    summarize_traces,
)


def _event(
    status="completed",
    ok=True,
    latency=100.0,
):
    return {
        "trace_id": "trace-1",
        "timestamp_utc": "2026-11-09T10:00:00+00:00",
        "status": status,
        "model": "qwen3:1.7b",
        "latency_ms": latency,
        "tools_used": [
            {
                "tool": "get_pipeline_status",
                "ok": ok,
                "error": None,
            }
        ],
    }


def test_missing_trace_file(tmp_path):
    assert load_traces(
        tmp_path / "missing.jsonl"
    ) == []


def test_sensitive_fields_are_not_exposed(tmp_path):
    path = tmp_path / "traces.jsonl"

    event = {
        **_event(),
        "question": "PRIVATE_QUESTION",
        "answer": "PRIVATE_ANSWER",
        "arguments": {
            "secret": "PRIVATE_ARGUMENT",
        },
    }

    path.write_text(
        json.dumps(event),
        encoding="utf-8",
    )

    traces = load_traces(path)

    assert len(traces) == 1
    assert "PRIVATE_QUESTION" not in str(traces)
    assert "PRIVATE_ANSWER" not in str(traces)
    assert "PRIVATE_ARGUMENT" not in str(traces)


def test_invalid_lines_are_ignored(tmp_path):
    path = tmp_path / "traces.jsonl"

    path.write_text(
        "not json\n"
        + json.dumps(_event())
        + "\n[]\n",
        encoding="utf-8",
    )

    assert len(load_traces(path)) == 1


def test_limit_keeps_latest_traces(tmp_path):
    path = tmp_path / "traces.jsonl"

    path.write_text(
        "\n".join(
            json.dumps({
                **_event(),
                "trace_id": str(number),
            })
            for number in range(4)
        ),
        encoding="utf-8",
    )

    traces = load_traces(
        path,
        limit=2,
    )

    assert [
        item["trace_id"]
        for item in traces
    ] == ["2", "3"]


def test_summary_counts_status_and_tool_errors():
    events = [
        {
            "status": "completed",
            "latency_ms": 100.0,
            "tools_used": [
                {
                    "tool": "get_pipeline_status",
                    "ok": True,
                },
            ],
        },
        {
            "status": "limit_reached",
            "latency_ms": 300.0,
            "tools_used": [
                {
                    "tool": "get_pipeline_status",
                    "ok": False,
                },
            ],
        },
    ]

    summary = summarize_traces(events)

    assert summary["total_runs"] == 2
    assert summary["completed_runs"] == 1
    assert summary["non_completed_runs"] == 1
    assert summary["tool_calls"] == 2
    assert summary["tool_errors"] == 1
    assert summary["mean_latency_ms"] == 200.0


def test_empty_summary():
    summary = summarize_traces([])

    assert summary["total_runs"] == 0
    assert summary["mean_latency_ms"] is None


def test_evaluation_reports(tmp_path):
    tools = tmp_path / "tools.json"
    quality = tmp_path / "quality.json"

    tools.write_text(
        json.dumps({
            "passed_runs": 2,
            "total_runs": 3,
        }),
        encoding="utf-8",
    )

    quality.write_text(
        json.dumps({
            "passed_cases": 3,
            "total_cases": 3,
        }),
        encoding="utf-8",
    )

    assert load_report_summary(
        tools,
        kind="tools",
    )["pass_rate"] == 0.6667

    assert load_report_summary(
        quality,
        kind="quality",
    )["pass_rate"] == 1.0


def test_invalid_reports_are_ignored(tmp_path):
    path = tmp_path / "invalid.json"

    path.write_text(
        "invalid",
        encoding="utf-8",
    )

    assert load_report_summary(
        path,
        kind="tools",
    ) is None

    with pytest.raises(ValueError):
        load_report_summary(
            path,
            kind="unexpected",
        )



def test_execution_mode_with_legacy_traces(tmp_path):
    path = tmp_path / "traces.jsonl"

    old_event = _event()

    new_event = {
        **_event(),
        "execution_mode": "local_ollama",
    }

    path.write_text(
        json.dumps(old_event)
        + "\n"
        + json.dumps(new_event)
        + "\n",
        encoding="utf-8",
    )

    traces = load_traces(path)

    assert traces[0]["execution_mode"] == "unclassified"
    assert traces[1]["execution_mode"] == "local_ollama"


def test_filter_traces_by_mode_status_and_tool():
    events = [
        {
            "execution_mode": "local_ollama",
            "status": "completed",
            "tools_used": [
                {"tool": "get_pipeline_status"},
            ],
        },
        {
            "execution_mode": "injected_client",
            "status": "limit_reached",
            "tools_used": [
                {"tool": "delete_everything"},
            ],
        },
    ]

    filtered = filter_traces(
        events,
        mode="local_ollama",
        status="completed",
        tool="get_pipeline_status",
    )

    assert len(filtered) == 1
    assert (
        filtered[0]["execution_mode"]
        == "local_ollama"
    )

    assert filter_traces(
        events,
        mode="local_ollama",
        tool="delete_everything",
    ) == []

    with pytest.raises(ValueError):
        filter_traces(
            events,
            mode="invalid_mode",
        )

