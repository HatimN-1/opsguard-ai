
"""Privacy-conscious observability for OpsGuard AI."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACE_FILE = PROJECT_ROOT / "logs" / "agent_traces.jsonl"

ALLOWED_EXECUTION_MODES = {
    "local_ollama",
    "injected_client",
    "unclassified",
}

ALLOWED_EVENT_TYPES = {
    "AGENT_STARTED",
    "LLM_REQUESTED",
    "LLM_RESPONDED",
    "TOOL_REQUESTED",
    "TOOL_COMPLETED",
    "AGENT_COMPLETED",
    "AGENT_FAILED",
    "LIMIT_REACHED",
}

KNOWN_TOOL_NAMES = {
    "get_pipeline_status",
    "get_model_metrics",
    "search_runbook",
    "prepare_incident_ticket",
}

ALLOWED_ERROR_CODES = {
    "INVALID_ARGUMENTS",
    "UNKNOWN_TOOL",
    "NOT_FOUND",
    "TOOL_EXECUTION_ERROR",
    "LLM_ERROR",
    "INVALID_RESPONSE",
    "LIMIT_REACHED",
    "OTHER_ERROR",
}

MAX_EVENTS_PER_TRACE = 32


def make_agent_event(
    event_type: str,
    *,
    step: int | None = None,
    tool: str | None = None,
    ok: bool | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Create an event containing approved metadata only."""

    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("Unsupported event type")

    event: dict[str, Any] = {
        "event_type": event_type,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }

    if step is not None:
        if type(step) is not int or not 1 <= step <= 4:
            raise ValueError("Invalid event step")

        event["step"] = step

    if tool is not None:
        event["tool"] = (
            tool
            if isinstance(tool, str)
            and tool in KNOWN_TOOL_NAMES
            else "unlisted_tool"
        )

    if ok is not None:
        if type(ok) is not bool:
            raise ValueError("Invalid tool outcome")

        event["ok"] = ok

    if error is not None:
        event["error"] = (
            error
            if isinstance(error, str)
            and error in ALLOWED_ERROR_CODES
            else "OTHER_ERROR"
        )

    return event


def _sanitize_event(
    raw: object,
) -> dict[str, Any] | None:
    """Whitelist event fields before writing them to disk."""

    if not isinstance(raw, dict):
        return None

    event_type = raw.get("event_type")

    if (
        not isinstance(event_type, str)
        or event_type not in ALLOWED_EVENT_TYPES
    ):
        return None

    timestamp = raw.get("timestamp_utc")

    if not isinstance(timestamp, str):
        return None

    try:
        parsed_time = datetime.fromisoformat(timestamp)

        if parsed_time.tzinfo is None:
            return None

        safe_timestamp = parsed_time.astimezone(
            UTC
        ).isoformat()

    except ValueError:
        return None

    event: dict[str, Any] = {
        "event_type": event_type,
        "timestamp_utc": safe_timestamp,
    }

    step = raw.get("step")

    if type(step) is int and 1 <= step <= 4:
        event["step"] = step

    if "tool" in raw:
        tool = raw.get("tool")

        event["tool"] = (
            tool
            if isinstance(tool, str)
            and tool in KNOWN_TOOL_NAMES
            else "unlisted_tool"
        )

    if type(raw.get("ok")) is bool:
        event["ok"] = raw["ok"]

    if "error" in raw:
        error = raw.get("error")

        event["error"] = (
            error
            if isinstance(error, str)
            and error in ALLOWED_ERROR_CODES
            else "OTHER_ERROR"
        )

    return event

def sanitize_event_timeline(
    raw_events: object,
) -> list[dict[str, Any]]:
    """Return only approved, bounded timeline events."""

    if not isinstance(raw_events, list):
        return []

    safe_events = []

    for raw in raw_events[:MAX_EVENTS_PER_TRACE]:
        safe_event = _sanitize_event(raw)

        if safe_event is not None:
            safe_events.append(safe_event)

    return safe_events


def record_agent_trace(
    result: dict[str, Any],
    latency_ms: float,
    *,
    path: Path | None = None,
    execution_mode: str = "unclassified",
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record execution metadata and optional event timeline."""

    trace_id = uuid4().hex
    duration = round(latency_ms, 2)

    if execution_mode not in ALLOWED_EXECUTION_MODES:
        execution_mode = "unclassified"

    # Retain the existing dashboard-compatible tool format.
    # Questions, answers and tool arguments are excluded.
    safe_tools = [
        {
            "tool": str(item.get("tool", ""))[:80],
            "ok": item.get("ok") is True,
            "error": item.get("error"),
        }
        for item in result.get("tools_used", [])
    ]

    trace: dict[str, Any] = {
        "trace_id": trace_id,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "execution_mode": execution_mode,
        "model": result.get("model"),
        "status": result.get("status"),
        "latency_ms": duration,
        "tool_call_count": len(safe_tools),
        "tools_used": safe_tools,
    }

    # Event timelines are optional for compatibility
    # with previous traces and existing tests.

    if events is not None:
        safe_events = sanitize_event_timeline(events)

        trace["events"] = safe_events
        trace["event_count"] = len(safe_events)


    destination = path if path is not None else TRACE_FILE

    try:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with destination.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    trace,
                    ensure_ascii=False,
                )
                + "\n"
            )

    except OSError:
        LOGGER.warning(
            "Unable to write agent trace",
            exc_info=True,
        )

    return {
        **result,
        "trace_id": trace_id,
        "latency_ms": duration,
    }
