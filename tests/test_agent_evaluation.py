
"""Tests for repeated agent evaluation."""

import pytest

from scripts.evaluate_agent import evaluate_cases

CASE = {
    "id": "EVAL-TEST",
    "question": "Check a pipeline",
    "expected_tools": ["get_pipeline_status"],
}


def make_response(tools, status="completed"):
    return {
        "status": status,
        "tools_used": [
            {
                "tool": name,
                "ok": True,
                "error": None,
            }
            for name in tools
        ],
        "latency_ms": 100.0,
        "trace_id": "test-trace",
    }


def test_repeated_evaluation():
    responses = iter([
        make_response(["get_pipeline_status"]),
        make_response([]),
    ])

    report = evaluate_cases(
        [CASE],
        repeats=2,
        agent_runner=lambda question: next(responses),
    )

    assert report["total_runs"] == 2
    assert report["passed_runs"] == 1
    assert report["exact_tool_match_rate"] == 0.5
    assert report["mean_latency_ms"] == 100.0
    assert report["results"][1]["missing_tools"] == [
        "get_pipeline_status"
    ]


def test_unexpected_tool_is_penalized():
    report = evaluate_cases(
        [CASE],
        repeats=1,
        agent_runner=lambda question: make_response([
            "get_pipeline_status",
            "search_runbook",
        ]),
    )

    assert report["passed_runs"] == 0
    assert report["results"][0]["unexpected_tools"] == [
        "search_runbook"
    ]


def test_invalid_repeat_count():
    with pytest.raises(ValueError):
        evaluate_cases(
            [CASE],
            repeats=0,
        )
