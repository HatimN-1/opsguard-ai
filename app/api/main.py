
"""OpsGuard AI HTTP API."""
#-----------------------------------------------------------------------------

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.diagnostic import diagnose_pipeline
from app.tools.incident_tool import (
    approve_ticket,
    request_ticket_creation,
)
from app.tools.model_monitor import get_model_metrics
from app.tools.pipeline_tool import get_pipeline_status
from app.tools.runbook_tool import search_runbook

#-----------------------------------------------------------------------------
app = FastAPI(title="OpsGuard AI", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return a stable response for health checks and CI smoke tests."""
    return {
        "status": "ok",
        "service": "OpsGuard AI",
        "version": "0.1.0",
    }


@app.get("/pipelines/{pipeline_id}")
def read_pipeline(pipeline_id: str) -> dict:
    """Retrieve a simulated pipeline or return HTTP 404."""
    pipeline = get_pipeline_status(pipeline_id)

    if pipeline is None:
        raise HTTPException(
            status_code=404,
            detail="Pipeline not found",
        )

    return pipeline


@app.get("/models/{model_id}/metrics")
def read_model_metrics(model_id: str) -> dict:
    """Return simulated monitoring metrics for a model."""

    metrics = get_model_metrics(model_id)

    if metrics is None:
        raise HTTPException(
            status_code=404,
            detail="Model not found",
        )

    return metrics


@app.get("/runbooks/search")
def read_runbooks(
    error_code: str = Query(
        ...,
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9_]+$",
    ),
) -> dict:
    """Find technical runbooks for a validated error code."""

    results = search_runbook(error_code)

    return {
        "error_code": error_code.upper(),
        "count": len(results),
        "results": results,
    }


class TicketRequest(BaseModel):
    """Validated payload for a simulated incident ticket."""

    incident_id: str = Field(
        pattern=r"^INC-[0-9]{3}$"
    )
    reason: str = Field(
        min_length=10,
        max_length=500,
    )


@app.post("/tickets", status_code=201)
def create_ticket(
    payload: TicketRequest,
    x_demo_user: str = Header(...),
) -> dict:
    """Submit a simulated ticket request for approval."""

    try:
        return request_ticket_creation(
            payload.incident_id,
            payload.reason,
            x_demo_user,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/tickets/{ticket_id}/approve")
def approve_ticket_endpoint(
    ticket_id: str,
    x_demo_user: str = Header(...),
) -> dict:
    """Simulate a separate approver authorizing a ticket."""

    try:
        return approve_ticket(
            ticket_id,
            x_demo_user,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.get("/diagnostics/pipelines/{pipeline_id}")
def read_pipeline_diagnosis(pipeline_id: str) -> dict:
    """Execute a deterministic pipeline diagnosis."""

    result = diagnose_pipeline(pipeline_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Pipeline not found",
        )

    return result
