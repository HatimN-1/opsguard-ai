
"""Read local OpsGuard AI observability data without sensitive content."""

import json
import math
from collections import Counter, deque
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]

TRACE_FILE = ROOT / "logs" / "agent_traces.jsonl"

TOOL_REPORT = (
    ROOT / "outputs" / "agent_evaluation_repeated.json"
)

QUALITY_REPORT = (
    ROOT / "outputs" / "response_quality.json"
)


def _safe_text(value: object, limit: int = 80) -> str:
    """Return bounded display text."""

    return value[:limit] if isinstance(value, str) else ""


def load_traces(
    path: Path | None = None,
    *,
    limit: int = 500,
) -> list[dict]:
    """Load safe trace metadata, keeping the newest records."""

    if not 1 <= limit <= 5000:
        raise ValueError(
            "limit must be between 1 and 5000"
        )

    source = path if path is not None else TRACE_FILE

    events: deque[dict] = deque(maxlen=limit)

    try:
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(raw, dict):
                    continue

                raw_tools = raw.get("tools_used", [])

                if not isinstance(raw_tools, list):
                    raw_tools = []

                # Only approved execution metadata is retained.
                safe_tools = [
                    {
                        "tool": _safe_text(
                            item.get("tool")
                        ),
                        "ok": item.get("ok") is True,
                        "error": _safe_text(
                            item.get("error")
                        ),
                    }
                    for item in raw_tools
                    if isinstance(item, dict)
                ][:4]

                latency = raw.get("latency_ms")

                if (
                    not isinstance(latency, (int, float))
                    or isinstance(latency, bool)
                    or not math.isfinite(latency)
                    or latency < 0
                ):
                    latency = None

                events.append({
                    "trace_id": _safe_text(
                        raw.get("trace_id"),
                        64,
                    ),
                    "timestamp_utc": _safe_text(
                        raw.get("timestamp_utc"),
                        40,
                    ),
                    "model": _safe_text(
                        raw.get("model")
                    ),
                    "status": _safe_text(
                        raw.get("status")
                    ),
                    "latency_ms": latency,
                    "tools_used": safe_tools,
                })

    except (OSError, UnicodeError):
        return []

    return list(events)


def summarize_traces(events: list[dict]) -> dict:
    """Calculate aggregate observability metrics."""

    statuses = Counter(
        event["status"]
        for event in events
    )

    tools = Counter(
        item["tool"]
        for event in events
        for item in event["tools_used"]
        if item["tool"]
    )

    errors = sum(
        item["ok"] is False
        for event in events
        for item in event["tools_used"]
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
        "tool_calls": sum(tools.values()),
        "tool_errors": errors,
        "mean_latency_ms": (
            round(mean(durations), 2)
            if durations
            else None
        ),
        "status_counts": dict(statuses),
        "tool_counts": dict(tools),
    }


def load_report_summary(
    path: Path,
    *,
    kind: str,
) -> dict | None:
    """Read only pass/total counts from evaluation reports."""

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

    if kind not in keys:
        raise ValueError(
            "Unsupported evaluation report kind"
        )

    try:
        report = json.loads(
            path.read_text(encoding="utf-8")
        )

    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(report, dict):
        return None

    passed_key, total_key = keys[kind]

    passed = report.get(passed_key)
    total = report.get(total_key)

    if (
        type(passed) is not int
        or type(total) is not int
        or total <= 0
        or not 0 <= passed <= total
    ):
        return None

    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(
            passed / total,
            4,
        ),
    }
