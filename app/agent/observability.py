
"""Privacy-conscious JSONL observability for OpsGuard AI."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACE_FILE = PROJECT_ROOT / "logs" / "agent_traces.jsonl"


def record_agent_trace(
    result: dict[str, Any],
    latency_ms: float,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Record execution metadata without prompts or answers."""

    trace_id = uuid4().hex
    duration = round(latency_ms, 2)

    safe_tools = [
        {
            "tool": str(item.get("tool", ""))[:80],
            "ok": item.get("ok") is True,
            "error": item.get("error"),
        }
        for item in result.get("tools_used", [])
    ]

    event = {
        "trace_id": trace_id,
        "timestamp_utc": datetime.now(
            UTC
        ).isoformat(),
        "model": result.get("model"),
        "status": result.get("status"),
        "latency_ms": duration,
        "tool_call_count": len(safe_tools),
        "tools_used": safe_tools,
    }

    destination = path if path is not None else TRACE_FILE

    try:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with destination.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(
                    event,
                    ensure_ascii=False,
                ) + "\n"
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
