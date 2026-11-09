
"""Read local OpsGuard AI observability data without sensitive content."""

import json
import math
from collections import Counter, deque
from pathlib import Path
from statistics import mean

# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

TRACE_FILE = (
    ROOT / "logs" / "agent_traces.jsonl"
)

TOOL_REPORT = (
    ROOT / "outputs" / "agent_evaluation_repeated.json"
)

QUALITY_REPORT = (
    ROOT / "outputs" / "response_quality.json"
)


# ---------------------------------------------------------------------
# Safe text conversion
# ---------------------------------------------------------------------

def _safe_text(
    value: object,
    limit: int = 80,
) -> str:
    """Return bounded display text."""

    if isinstance(value, str):
        return value[:limit]

    return ""


# ---------------------------------------------------------------------
# Load local JSONL traces
# ---------------------------------------------------------------------

def load_traces(
    path: Path | None = None,
    *,
    limit: int = 500,
) -> list[dict]:
    """Load safe metadata from the newest local agent traces."""

    if not 1 <= limit <= 5000:
        raise ValueError(
            "limit must be between 1 and 5000"
        )

    source = (
        path
        if path is not None
        else TRACE_FILE
    )

    events: deque[dict] = deque(
        maxlen=limit
    )

    try:
        with source.open(
            encoding="utf-8"
        ) as handle:

            for line in handle:

                # -------------------------------------------------
                # Decode one JSONL event
                # -------------------------------------------------

                try:
                    raw = json.loads(line)

                except json.JSONDecodeError:
                    continue

                if not isinstance(raw, dict):
                    continue

                # -------------------------------------------------
                # Read safe tool execution metadata
                # -------------------------------------------------

                raw_tools = raw.get(
                    "tools_used",
                    [],
                )

                if not isinstance(
                    raw_tools,
                    list,
                ):
                    raw_tools = []

                safe_tools = [
                    {
                        "tool": _safe_text(
                            item.get("tool")
                        ),
                        "ok": (
                            item.get("ok") is True
                        ),
                        "error": _safe_text(
                            item.get("error")
                        ),
                    }
                    for item in raw_tools
                    if isinstance(item, dict)
                ][:4]

                # -------------------------------------------------
                # Validate the latency
                # -------------------------------------------------

                latency = raw.get(
                    "latency_ms"
                )

                if (
                    not isinstance(
                        latency,
                        (int, float),
                    )
                    or isinstance(
                        latency,
                        bool,
                    )
                    or not math.isfinite(
                        latency
                    )
                    or latency < 0
                ):
                    latency = None

                # -------------------------------------------------
                # Determine execution origin
                #
                # Older traces do not include execution_mode.
                # They must remain unclassified.
                # -------------------------------------------------

                execution_mode = raw.get(
                    "execution_mode"
                )

                if execution_mode not in (
                    "local_ollama",
                    "injected_client",
                ):
                    execution_mode = (
                        "unclassified"
                    )

                # -------------------------------------------------
                # Keep only approved observability fields
                #
                # Never retain:
                # - User questions
                # - Generated answers
                # - Tool arguments
                # - Secrets
                # -------------------------------------------------

                events.append({
                    "trace_id": _safe_text(
                        raw.get("trace_id"),
                        64,
                    ),
                    "timestamp_utc": _safe_text(
                        raw.get(
                            "timestamp_utc"
                        ),
                        40,
                    ),
                    "model": _safe_text(
                        raw.get("model")
                    ),
                    "status": _safe_text(
                        raw.get("status")
                    ),
                    "execution_mode": (
                        execution_mode
                    ),
                    "latency_ms": latency,
                    "tools_used": safe_tools,
                })

    except (
        OSError,
        UnicodeError,
    ):
        return []

    return list(events)


# ---------------------------------------------------------------------
# Filter agent traces
# ---------------------------------------------------------------------

def filter_traces(
    events: list[dict],
    *,
    mode: str = "all",
    status: str = "all",
    tool: str = "all",
) -> list[dict]:
    """Filter traces by execution mode, status and tool."""

    allowed_modes = (
        "all",
        "local_ollama",
        "injected_client",
        "unclassified",
    )

    if mode not in allowed_modes:
        raise ValueError(
            "Unsupported execution mode"
        )

    filtered_events = []

    for event in events:

        # -------------------------------------------------
        # Filter by execution mode
        # -------------------------------------------------

        event_mode = event.get(
            "execution_mode",
            "unclassified",
        )

        if (
            mode != "all"
            and event_mode != mode
        ):
            continue

        # -------------------------------------------------
        # Filter by agent status
        # -------------------------------------------------

        event_status = event.get(
            "status"
        )

        if (
            status != "all"
            and event_status != status
        ):
            continue

        # -------------------------------------------------
        # Filter by tool name
        # -------------------------------------------------

        if tool != "all":

            tools_used = event.get(
                "tools_used",
                [],
            )

            tool_found = any(
                item.get("tool") == tool
                for item in tools_used
            )

            if not tool_found:
                continue

        filtered_events.append(
            event
        )

    return filtered_events


# ---------------------------------------------------------------------
# Aggregate observability metrics
# ---------------------------------------------------------------------


def summarize_traces(
    events: list[dict],
) -> dict:
    """Calculate execution and tool-outcome metrics."""

    statuses = Counter(
        event["status"]
        for event in events
    )

    # Count successful and failed tool calls separately.
    tool_outcomes: dict[str, dict[str, int]] = {}

    for event in events:
        for item in event["tools_used"]:
            name = item.get("tool")

            if not name:
                continue

            if name not in tool_outcomes:
                tool_outcomes[name] = {
                    "success": 0,
                    "failed": 0,
                }

            outcome = (
                "success"
                if item.get("ok") is True
                else "failed"
            )

            tool_outcomes[name][outcome] += 1

    tool_successes = sum(
        counts["success"]
        for counts in tool_outcomes.values()
    )

    tool_errors = sum(
        counts["failed"]
        for counts in tool_outcomes.values()
    )

    tool_calls = tool_successes + tool_errors

    error_rate = (
        round(100 * tool_errors / tool_calls, 2)
        if tool_calls
        else None
    )

    durations = [
        event["latency_ms"]
        for event in events
        if event["latency_ms"] is not None
    ]

    return {
        "total_runs": len(events),
        "completed_runs": statuses["completed"],
        "non_completed_runs": (
            len(events) - statuses["completed"]
        ),
        "tool_calls": tool_calls,
        "tool_successes": tool_successes,
        "tool_errors": tool_errors,
        "tool_error_rate_pct": error_rate,
        "mean_latency_ms": (
            round(mean(durations), 2)
            if durations
            else None
        ),
        "status_counts": dict(statuses),
        "tool_counts": {
            name: counts["success"] + counts["failed"]
            for name, counts in tool_outcomes.items()
        },
        "tool_outcomes": dict(sorted(tool_outcomes.items())),
    }

# ---------------------------------------------------------------------
# Load local evaluation reports
# ---------------------------------------------------------------------

def load_report_summary(
    path: Path,
    *,
    kind: str,
) -> dict | None:
    """Read only safe counts from local evaluation reports."""

    keys = {
        "tools": (
            "passed_runs",
            "total_runs",
        ),
        "quality": (
            "passed_cases",
            "total_cases",
        ),
    }

    # -------------------------------------------------------------
    # Validate evaluation type
    # -------------------------------------------------------------

    if kind not in keys:
        raise ValueError(
            "Unsupported evaluation report kind"
        )

    # -------------------------------------------------------------
    # Read the local JSON report
    # -------------------------------------------------------------

    try:
        report = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(
        report,
        dict,
    ):
        return None

    # -------------------------------------------------------------
    # Extract the expected count fields
    # -------------------------------------------------------------

    passed_key, total_key = (
        keys[kind]
    )

    passed = report.get(
        passed_key
    )

    total = report.get(
        total_key
    )

    # -------------------------------------------------------------
    # Validate counts
    # -------------------------------------------------------------

    if (
        type(passed) is not int
        or type(total) is not int
        or total <= 0
        or not 0 <= passed <= total
    ):
        return None

    # -------------------------------------------------------------
    # Return safe summary only
    # -------------------------------------------------------------

    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(
            passed / total,
            4,
        ),
    }
