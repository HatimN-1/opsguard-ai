"""Allowlisted, validated tools available to the local LLM."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.adf_monitor.business_escalation import EscalationError, prepare_case
from app.adf_monitor.company_monitor import list_business_runs
from app.adf_monitor.doc_search import search_official_docs
from app.adf_monitor.source import SourceUnavailable, query_adf_logs
from app.tools.incident_tool import INCIDENTS_FILE
from app.tools.model_monitor import get_model_metrics
from app.tools.pipeline_log_tool import get_pipeline_logs
from app.tools.pipeline_tool import get_pipeline_status
from app.tools.runbook_tool import search_runbook


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PipelineArgs(StrictArgs):
    pipeline_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9_]+$")


class ModelArgs(StrictArgs):
    model_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9_]+$")


class RunbookArgs(StrictArgs):
    error_code: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_]+$")


class TicketProposalArgs(StrictArgs):
    incident_id: str = Field(pattern=r"^INC-[0-9]{3}$")
    reason: str = Field(min_length=10, max_length=500)


class PipelineLogArgs(StrictArgs):
    pipeline_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9_]+$")
    run_id: str = Field(default="latest", pattern=r"^(latest|SIM-[0-9a-f]{12})$")


class AdfQueryArgs(StrictArgs):
    pipeline_name: str | None = Field(
        default=None, min_length=3, max_length=80,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]{2,79}$",
    )
    run_id: str | None = Field(
        default=None, min_length=1, max_length=100,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    hours: int = Field(default=72, ge=1, le=720)
    limit: int = Field(default=200, ge=1, le=500)
    error_codes: list[str] | None = Field(default=None, max_length=10)
    excluded_error_codes: list[str] | None = Field(default=None, max_length=10)


class AdfEscalationArgs(StrictArgs):
    pipeline_id: str = Field(
        pattern=r"^adf_(?:0[1-9]|1[0-2])_(?:orders|customers|payments|inventory)$"
    )
    run_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    reason: str = Field(min_length=15, max_length=300)


class OfficialDocsArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=500)
    error_code: str | None = Field(
        default=None, min_length=1, max_length=80,
        pattern=r"^[A-Za-z0-9_]+$",
    )
    limit: int = Field(default=3, ge=1, le=5)


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_pipeline_status": PipelineArgs,
    "get_model_metrics": ModelArgs,
    "search_runbook": RunbookArgs,
    "prepare_incident_ticket": TicketProposalArgs,
    "get_pipeline_logs": PipelineLogArgs,
    "query_adf_logs": AdfQueryArgs,
    "search_official_docs": OfficialDocsArgs,
    "prepare_adf_escalation": AdfEscalationArgs,
}

TOOL_DESCRIPTIONS = {
    "get_pipeline_status": "Read the recorded status of a simulated ETL pipeline.",
    "get_model_metrics": "Read simulated ML inference metrics for a model.",
    "search_runbook": "Search documented troubleshooting procedures by error code.",
    "prepare_incident_ticket": (
        "Prepare a ticket proposal for human approval. Does NOT create or approve any ticket."
    ),
    "query_adf_logs": (
        "Read bounded metadata from external ADF-like JSONL or an authorized "
        "Azure Log Analytics workspace. Read only, no arbitrary paths."
    ),
    "search_official_docs": (
        "Retrieve cited Microsoft Learn guidance from a local documentation "
        "index using lexical ranking. Read only; may return no match."
    ),
    "prepare_adf_escalation": (
        "Prepare a read-only escalation PROPOSAL for a known failed ADF run. "
        "Never create, request, approve or execute an incident or pipeline change."
    ),
    "get_pipeline_logs": (
        "Read a bounded simulated execution journal for a known pipeline. "
        "Supply pipeline_id and optionally run_id='latest' or a SIM-... identifier. "
        "Returns verified event categories and metrics but never raw log messages. "
        "Read-only; cannot execute or restart pipelines."
    ),
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "parameters": model.model_json_schema(),
        },
    }
    for name, model in TOOL_MODELS.items()
]


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate every request before executing an allowlisted tool."""
    schema = TOOL_MODELS.get(name)
    if schema is None:
        return {"ok": False, "tool": name, "error": "UNKNOWN_TOOL"}
    try:
        parsed = schema.model_validate(arguments)
    except ValidationError:
        return {"ok": False, "tool": name, "error": "INVALID_ARGUMENTS"}
    values = parsed.model_dump()

    if name == "get_pipeline_status":
        result = get_pipeline_status(values["pipeline_id"])
    elif name == "get_model_metrics":
        result = get_model_metrics(values["model_id"])
    elif name == "search_runbook":
        result = search_runbook(values["error_code"])
    elif name == "get_pipeline_logs":
        result = get_pipeline_logs(values["pipeline_id"], values["run_id"])
    elif name == "query_adf_logs":
        try:
            result = query_adf_logs(**values)
        except SourceUnavailable:
            return {"ok": False, "tool": name, "error": "SOURCE_UNAVAILABLE"}
        if result["matching_events"] == 0:
            return {"ok": False, "tool": name, "error": "NOT_FOUND"}
    elif name == "search_official_docs":
        result = search_official_docs(**values)
    elif name == "prepare_adf_escalation":
        try:
            failed_run = any(
                run["pipeline_name"] == values["pipeline_id"]
                and run["run_id"] == values["run_id"]
                and run["status"] == "Failed"
                for run in list_business_runs(hours=720)
            )
            if not failed_run:
                return {"ok": False, "tool": name, "error": "NOT_FOUND"}
            result = prepare_case(**values)
        except SourceUnavailable:
            return {"ok": False, "tool": name, "error": "SOURCE_UNAVAILABLE"}
        except (EscalationError, ValueError, OSError):
            return {"ok": False, "tool": name, "error": "INVALID_ARGUMENTS"}
    else:
        with INCIDENTS_FILE.open(encoding="utf-8") as handle:
            incidents = json.load(handle)
        exists = any(
            item["incident_id"] == values["incident_id"] for item in incidents
        )
        if not exists:
            return {"ok": False, "tool": name, "error": "NOT_FOUND"}
        result = {
            "incident_id": values["incident_id"],
            "reason": values["reason"],
            "status": "PROPOSAL_ONLY",
            "human_approval_required": True,
            "ticket_created": False,
        }

    if result is None or result == []:
        return {"ok": False, "tool": name, "error": "NOT_FOUND"}
    return {"ok": True, "tool": name, "data": result}
