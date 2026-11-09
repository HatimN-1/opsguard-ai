
"""Allowlisted, validated tools available to the local LLM."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.incident_tool import INCIDENTS_FILE
from app.tools.model_monitor import get_model_metrics
from app.tools.pipeline_tool import get_pipeline_status
from app.tools.runbook_tool import search_runbook


class StrictArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class PipelineArgs(StrictArgs):
    pipeline_id: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )


class ModelArgs(StrictArgs):
    model_id: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )


class RunbookArgs(StrictArgs):
    error_code: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9_]+$",
    )


class TicketProposalArgs(StrictArgs):
    incident_id: str = Field(
        pattern=r"^INC-[0-9]{3}$",
    )
    reason: str = Field(
        min_length=10,
        max_length=500,
    )


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_pipeline_status": PipelineArgs,
    "get_model_metrics": ModelArgs,
    "search_runbook": RunbookArgs,
    "prepare_incident_ticket": TicketProposalArgs,
}

TOOL_DESCRIPTIONS = {
    "get_pipeline_status": (
        "Read the recorded status of a simulated ETL pipeline."
    ),
    "get_model_metrics": (
        "Read simulated ML inference metrics for a model."
    ),
    "search_runbook": (
        "Search documented troubleshooting procedures by error code."
    ),
    "prepare_incident_ticket": (
        "Prepare a ticket proposal for human approval. "
        "Does NOT create or approve any ticket."
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


def execute_tool(
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Validate an allowlisted tool request."""

    schema = TOOL_MODELS.get(name)

    if schema is None:
        return {
            "ok": False,
            "tool": name,
            "error": "UNKNOWN_TOOL",
        }

    try:
        parsed = schema.model_validate(arguments)
    except ValidationError:
        return {
            "ok": False,
            "tool": name,
            "error": "INVALID_ARGUMENTS",
        }

    values = parsed.model_dump()

    if name == "get_pipeline_status":
        result = get_pipeline_status(
            values["pipeline_id"]
        )

    elif name == "get_model_metrics":
        result = get_model_metrics(
            values["model_id"]
        )

    elif name == "search_runbook":
        result = search_runbook(
            values["error_code"]
        )

    else:
        with INCIDENTS_FILE.open(
            encoding="utf-8"
        ) as handle:
            incidents = json.load(handle)

        exists = any(
            item["incident_id"] == values["incident_id"]
            for item in incidents
        )

        if not exists:
            return {
                "ok": False,
                "tool": name,
                "error": "NOT_FOUND",
            }

        result = {
            "incident_id": values["incident_id"],
            "reason": values["reason"],
            "status": "PROPOSAL_ONLY",
            "human_approval_required": True,
            "ticket_created": False,
        }

    if result is None or result == []:
        return {
            "ok": False,
            "tool": name,
            "error": "NOT_FOUND",
        }

    return {
        "ok": True,
        "tool": name,
        "data": result,
    }
