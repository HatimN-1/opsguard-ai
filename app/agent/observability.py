"""Privacy-conscious observability for OpsGuard AI."""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACE_FILE = PROJECT_ROOT / "logs" / "agent_traces.jsonl"

ALLOWED_EXECUTION_MODES = {"local_ollama", "injected_client", "unclassified", "deterministic_retrieval", "enterprise_llm"}
ALLOWED_EVENT_TYPES = {
    "AGENT_STARTED", "LLM_REQUESTED", "LLM_RESPONDED", "TOOL_REQUESTED",
    "TOOL_COMPLETED", "AGENT_COMPLETED", "AGENT_FAILED", "LIMIT_REACHED",
    "REQUEST_REJECTED", "ESCALATION_PROPOSED",
}
KNOWN_TOOL_NAMES = {
    "get_pipeline_status", "get_model_metrics", "search_runbook",
    "prepare_incident_ticket", "get_pipeline_logs", "query_adf_logs",
    "search_official_docs", "prepare_adf_escalation",
}
ALLOWED_ERROR_CODES = {
    "INVALID_ARGUMENTS", "UNKNOWN_TOOL", "NOT_FOUND", "TOOL_EXECUTION_ERROR",
    "LLM_ERROR", "INVALID_RESPONSE", "LIMIT_REACHED", "OTHER_ERROR",
    "SOURCE_UNAVAILABLE",
}
MAX_EVENTS_PER_TRACE = 32
ALLOWED_SELECTION_SOURCES = {"evidence_plan", "llm_proposed", "policy", "user_explicit"}
ALLOWED_REASON_CODES = {
    "UNAUTHORIZED_ACTION", "AMBIGUOUS_SCOPE", "INVALID_REQUEST",
    "SOURCE_NOT_ALLOWED", "NO_SUCH_RUN", "PROPOSAL_PREPARED",
}
ALLOWED_OUTCOME_CATEGORIES = {
    "SUCCESS", "NOT_FOUND", "INVALID_ARGUMENTS", "TOOL_ERROR", "PROPOSAL_ONLY",
}


def _safe_arguments(tool: str | None, arguments: object) -> dict[str, Any]:
    """Persist a bounded allowlist of operational arguments, NEVER raw prompts or reasons."""
    if not isinstance(arguments, dict):
        return {}
    safe: dict[str, Any] = {}
    if tool in {"query_adf_logs", "prepare_adf_escalation"}:
        pipeline = arguments.get("pipeline_name", arguments.get("pipeline_id"))
        if isinstance(pipeline, str) and re.fullmatch(
            r"adf_(?:0[1-9]|1[0-2])_(?:orders|customers|payments|inventory)", pipeline
        ):
            safe["pipeline_id"] = pipeline
        run_id = arguments.get("run_id")
        if isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", run_id):
            safe["run_id_sha256_12"] = hashlib.sha256(run_id.encode()).hexdigest()[:12]
        if tool == "prepare_adf_escalation":
            safe["reason_redacted"] = True
    if tool == "query_adf_logs":
        for field, limit in (("hours", 720), ("limit", 500)):
            value = arguments.get(field)
            if type(value) is int and 1 <= value <= limit:
                safe[field] = value
        for field in ("error_codes", "excluded_error_codes"):
            codes = arguments.get(field)
            if isinstance(codes, list) and len(codes) <= 10:
                filtered = [x for x in codes if isinstance(x, str)
                            and re.fullmatch(r"[A-Za-z0-9_]{1,40}", x)]
                if len(filtered) == len(codes):
                    safe[field] = filtered
    if tool == "search_official_docs":
        code = arguments.get("error_code")
        if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,40}", code):
            safe["error_code"] = code
        value = arguments.get("limit")
        if type(value) is int and 1 <= value <= 5:
            safe["limit"] = value
        safe["query_redacted"] = True
    return safe



def make_agent_event(
    event_type: str,
    *,
    step: int | None = None,
    tool: str | None = None,
    ok: bool | None = None,
    error: str | None = None,
    selection_source: str | None = None,
    arguments: dict[str, Any] | None = None,
    duration_ms: float | None = None,
    outcome_category: str | None = None,
    reason_code: str | None = None,
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
            tool if isinstance(tool, str) and tool in KNOWN_TOOL_NAMES else "unlisted_tool"
        )
    if ok is not None:
        if type(ok) is not bool:
            raise ValueError("Invalid tool outcome")
        event["ok"] = ok
    if error is not None:
        event["error"] = (
            error
            if isinstance(error, str) and error in ALLOWED_ERROR_CODES
            else "OTHER_ERROR"
        )
    if selection_source in ALLOWED_SELECTION_SOURCES:
        event["selection_source"] = selection_source
    if arguments is not None:
        event["arguments_safe"] = _safe_arguments(tool, arguments)
    if duration_ms is not None and isinstance(duration_ms, (int, float)) and 0 <= duration_ms <= 3_600_000:
        event["duration_ms"] = round(duration_ms, 2)
    if outcome_category in ALLOWED_OUTCOME_CATEGORIES:
        event["outcome_category"] = outcome_category
    if reason_code in ALLOWED_REASON_CODES:
        event["reason_code"] = reason_code
    return event


def _sanitize_event(raw: object) -> dict[str, Any] | None:
    """Whitelist event fields before writing them to disk."""
    if not isinstance(raw, dict):
        return None
    event_type = raw.get("event_type")
    if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
        return None
    timestamp = raw.get("timestamp_utc")
    if not isinstance(timestamp, str):
        return None
    try:
        parsed_time = datetime.fromisoformat(timestamp)
        if parsed_time.tzinfo is None:
            return None
        safe_timestamp = parsed_time.astimezone(UTC).isoformat()
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
            tool if isinstance(tool, str) and tool in KNOWN_TOOL_NAMES else "unlisted_tool"
        )
    if type(raw.get("ok")) is bool:
        event["ok"] = raw["ok"]
    if "error" in raw:
        error = raw.get("error")
        event["error"] = (
            error
            if isinstance(error, str) and error in ALLOWED_ERROR_CODES
            else "OTHER_ERROR"
        )
    if raw.get("selection_source") in ALLOWED_SELECTION_SOURCES:
        event["selection_source"] = raw["selection_source"]
    if "arguments_safe" in raw:
        # Re-sanitize regardless of what the caller passed into this event.
        # Accept only the output of _safe_arguments; original raw query/reason omitted.
        raw_safe = raw["arguments_safe"]
        if isinstance(raw_safe, dict):
            allowed = {"pipeline_id", "run_id_sha256_12", "reason_redacted", "hours",
                       "limit", "error_codes", "excluded_error_codes", "error_code",
                       "query_redacted"}
            event["arguments_safe"] = {
                k: v for k, v in raw_safe.items()
                if k in allowed and (
                    (k == "pipeline_id" and isinstance(v, str) and re.fullmatch(
                        r"adf_(?:0[1-9]|1[0-2])_(?:orders|customers|payments|inventory)", v))
                    or (k == "run_id_sha256_12" and isinstance(v, str) and
                        re.fullmatch(r"[0-9a-f]{12}", v))
                    or (k in {"reason_redacted", "query_redacted"} and v is True)
                    or (k == "hours" and type(v) is int and 1 <= v <= 720)
                    or (k == "limit" and type(v) is int and 1 <= v <= 500)
                    or (k == "error_code" and isinstance(v, str) and
                        re.fullmatch(r"[A-Za-z0-9_]{1,40}", v))
                    or (k in {"error_codes", "excluded_error_codes"} and
                        isinstance(v, list) and len(v) <= 10 and all(
                            isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_]{1,40}", x)
                            for x in v))
                )
            }
    if "duration_ms" in raw:
        value = raw["duration_ms"]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 3_600_000:
            event["duration_ms"] = round(value, 2)
    if raw.get("outcome_category") in ALLOWED_OUTCOME_CATEGORIES:
        event["outcome_category"] = raw["outcome_category"]
    if raw.get("reason_code") in ALLOWED_REASON_CODES:
        event["reason_code"] = raw["reason_code"]
    return event


def sanitize_event_timeline(raw_events: object) -> list[dict[str, Any]]:
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
    safe_tools = [
        {
            "tool": item.get("tool") if item.get("tool") in KNOWN_TOOL_NAMES
            else "unlisted_tool",
            "ok": item.get("ok") is True,
            "error": item.get("error") if item.get("error") in ALLOWED_ERROR_CODES
            else ("OTHER_ERROR" if item.get("error") is not None else None),
            "selection_source": item.get("selection_source") if
            item.get("selection_source") in ALLOWED_SELECTION_SOURCES else None,
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
        "iteration_count": max(0, min(4, int(result.get("iteration_count", len(safe_tools))))),
        "escalation_decision": result.get("escalation_decision") if
        result.get("escalation_decision") in {"NONE", "PROPOSAL_ONLY", "REFUSED"}
        else "NONE",
        "final_response_status": result.get("status") if result.get("status") in {
            "completed", "rejected", "no_matching_events", "source_unavailable",
            "invalid_response", "limit_reached", "llm_error", "failed",
        } else "other",
        "response_text_recorded": False,
        "tools_used": safe_tools,
    }
    if events is not None:
        safe_events = sanitize_event_timeline(events)
        trace["events"] = safe_events
        trace["event_count"] = len(safe_events)
    destination = path if path is not None else TRACE_FILE
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace, ensure_ascii=False) + "\n")
    except OSError:
        LOGGER.warning("Unable to write agent trace", exc_info=True)
    return {**result, "trace_id": trace_id, "latency_ms": duration}
