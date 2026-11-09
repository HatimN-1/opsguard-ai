
"""Tests for the safe tool registry."""

from app.agent.tool_registry import TOOL_SCHEMAS, execute_tool


def test_four_tools_declared() -> None:
    names = {
        item["function"]["name"]
        for item in TOOL_SCHEMAS
    }

    assert names == {
        "get_pipeline_status",
        "get_model_metrics",
        "search_runbook",
        "prepare_incident_ticket",
    }


def test_pipeline_tool() -> None:
    result = execute_tool(
        "get_pipeline_status",
        {"pipeline_id": "etl_orders_daily"},
    )

    assert result["ok"] is True
    assert result["data"]["status"] == "FAILED"


def test_model_tool() -> None:
    result = execute_tool(
        "get_model_metrics",
        {"model_id": "fraud_detection_v1"},
    )

    assert result["ok"] is True
    assert result["data"]["error_rate_pct"] == 4.5


def test_runbook_tool() -> None:
    result = execute_tool(
        "search_runbook",
        {"error_code": "SCHEMA_VALIDATION_ERROR"},
    )

    assert result["ok"] is True
    assert result["data"][0]["runbook_id"] == "RB-001"


def test_ticket_is_only_a_proposal() -> None:
    result = execute_tool(
        "prepare_incident_ticket",
        {
            "incident_id": "INC-001",
            "reason": "Investigate pipeline schema mismatch",
        },
    )

    assert result["ok"] is True
    assert result["data"]["ticket_created"] is False
    assert result["data"]["human_approval_required"] is True


def test_unknown_tool_rejected() -> None:
    result = execute_tool("delete_everything", {})

    assert result["error"] == "UNKNOWN_TOOL"


def test_invalid_arguments_rejected() -> None:
    result = execute_tool(
        "get_pipeline_status",
        {
            "pipeline_id": "etl_orders_daily",
            "unexpected": 123,
        },
    )

    assert result["error"] == "INVALID_ARGUMENTS"


def test_missing_resource_rejected() -> None:
    result = execute_tool(
        "get_pipeline_status",
        {"pipeline_id": "unknown"},
    )

    assert result["error"] == "NOT_FOUND"
