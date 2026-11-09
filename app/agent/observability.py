
"""Privacy-conscious JSONL observability for OpsGuard AI."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TRACE_FILE = (
    PROJECT_ROOT / "logs" / "agent_traces.jsonl"
)

ALLOWED_EXECUTION_MODES = {
    "local_ollama",
    "injected_client",
    "unclassified",
}


# ---------------------------------------------------------------------
# Record agent execution metadata
# ---------------------------------------------------------------------

def record_agent_trace(
    result: dict[str, Any],
    latency_ms: float,
    *,
    path: Path | None = None,
    execution_mode: str = "unclassified",
) -> dict[str, Any]:
    """Record safe execution metadata without prompts or answers."""

    # -------------------------------------------------------------
    # Generate trace identifiers and timing
    # -------------------------------------------------------------

    trace_id = uuid4().hex

    duration = round(
        latency_ms,
        2,
    )

    # -------------------------------------------------------------
    # Validate execution origin
    #
    # local_ollama:
    #     The default local Ollama client was used.
    #
    # injected_client:
    #     A client was supplied explicitly, commonly in tests.
    #
    # unclassified:
    #     Origin is not available or not recognized.
    # -------------------------------------------------------------

    if execution_mode not in ALLOWED_EXECUTION_MODES:
        execution_mode = "unclassified"

    # -------------------------------------------------------------
    # Collect safe tool execution metadata
    #
    # Do not store:
    # - Tool arguments
    # - User questions
    # - Generated responses
    # - Tool result contents
    # -------------------------------------------------------------

    safe_tools = [
        {
            "tool": str(
                item.get("tool", "")
            )[:80],
            "ok": (
                item.get("ok") is True
            ),
            "error": item.get("error"),
        }
        for item in result.get(
            "tools_used",
            [],
        )
    ]

    # -------------------------------------------------------------
    # Build the JSONL event
    # -------------------------------------------------------------

    event = {
        "trace_id": trace_id,
        "timestamp_utc": datetime.now(
            UTC
        ).isoformat(),
        "execution_mode": execution_mode,
        "model": result.get("model"),
        "status": result.get("status"),
        "latency_ms": duration,
        "tool_call_count": len(safe_tools),
        "tools_used": safe_tools,
    }

    # -------------------------------------------------------------
    # Determine log destination
    # -------------------------------------------------------------

    destination = (
        path
        if path is not None
        else TRACE_FILE
    )

    # -------------------------------------------------------------
    # Write one JSON event per line
    # -------------------------------------------------------------

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
                )
                + "\n"
            )

    except OSError:
        LOGGER.warning(
            "Unable to write agent trace",
            exc_info=True,
        )

    # -------------------------------------------------------------
    # Return the original agent result with observability metadata
    # -------------------------------------------------------------

    return {
        **result,
        "trace_id": trace_id,
        "latency_ms": duration,
    }
