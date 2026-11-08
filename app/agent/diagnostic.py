
"""Deterministic diagnostic orchestration for OpsGuard AI."""

from app.tools.pipeline_tool import get_pipeline_status
from app.tools.runbook_tool import search_runbook


def diagnose_pipeline(pipeline_id: str) -> dict | None:
    """Diagnose a simulated ETL pipeline using available tools."""

    pipeline = get_pipeline_status(pipeline_id)

    if pipeline is None:
        return None

    tools_used = ["get_pipeline_status"]
    error_code = pipeline.get("error_code")

    runbooks = []

    if error_code:
        runbooks = search_runbook(error_code)
        tools_used.append("search_runbook")

    return {
        "pipeline_id": pipeline["pipeline_id"],
        "pipeline_name": pipeline["name"],
        "status": pipeline["status"],
        "error_code": error_code,
        "runbooks": runbooks,
        "tools_used": tools_used,
        "ticket_created": False,
        "data_mode": "simulated",
    }
