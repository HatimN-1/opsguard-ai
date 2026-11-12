"""Bounded and read-only retrieval of *simulated* MLOps execution journals.

Journal strings are untrusted. The agent-facing reader returns only a small
allowlist of validated structural fields; free-form message text is excluded.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIMULATED_LOG_DIR = PROJECT_ROOT / "logs" / "simulated_pipelines"

RUN_ID_PATTERN = re.compile(r"SIM-[0-9a-f]{12}\Z")
PIPELINE_PATTERN = re.compile(r"[a-z0-9_]{3,80}\Z")
ALLOWED_SCENARIOS = {
    "success", "schema_error", "missing_values", "high_latency", "unknown_error"
}
ALLOWED_STATUSES = {"SUCCESS", "FAILED", "WARNING"}
ALLOWED_LEVELS = {"INFO", "WARNING", "ERROR"}
ALLOWED_STEPS = {"EXTRACT", "TRANSFORM", "LOAD", "MONITOR"}
ALLOWED_EVENTS = {
    "RUN_STARTED", "DATA_EXTRACTED", "SCHEMA_VALIDATED", "DATA_VALIDATED",
    "DATA_LOADED", "SCHEMA_MISMATCH", "MISSING_VALUES_DETECTED",
    "HIGH_LATENCY_DETECTED", "UNKNOWN_ERROR_DETECTED", "RUN_FINISHED",
}
ALLOWED_ERROR_CODES = {
    "SCHEMA_VALIDATION_ERROR", "MISSING_VALUES", "HIGH_LATENCY",
    "RESOURCE_CONTENTION_XYZ_999",
}
MAX_LOG_BYTES = 24_000
MAX_EVENTS = 20
MAX_VISIBLE_RUNS = 50


def _known_pipeline_ids() -> set[str]:
    """Never allow an arbitrary local path to be selected as a pipeline."""
    try:
        source = PROJECT_ROOT / "data" / "pipelines.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            return set()
        return {
            row["pipeline_id"]
            for row in records
            if isinstance(row, dict)
            and isinstance(row.get("pipeline_id"), str)
            and PIPELINE_PATTERN.fullmatch(row["pipeline_id"])
        }
    except (OSError, UnicodeError, ValueError):
        return set()


def is_known_pipeline(pipeline_id: str) -> bool:
    return (
        isinstance(pipeline_id, str)
        and bool(PIPELINE_PATTERN.fullmatch(pipeline_id))
        and pipeline_id in _known_pipeline_ids()
    )


def _run_file(pipeline_id: str, run_id: str, *, root: Path) -> Path | None:
    if not is_known_pipeline(pipeline_id):
        return None
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        return None
    # Both components have been validated; no user supplied paths are accepted.
    return root / f"{pipeline_id}__{run_id}.jsonl"


def _read_events(path: Path, run_id: str, pipeline_id: str) -> list[dict] | None:
    """Reject oversize, malformed, linked or inconsistent files entirely."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
            return None
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines(MAX_LOG_BYTES + 1)
    except (OSError, UnicodeError):
        return None
    if not 2 <= len(lines) <= MAX_EVENTS or sum(map(len, lines)) > MAX_LOG_BYTES:
        return None
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            return None
        if not isinstance(event, dict):
            return None
        if event.get("run_id") != run_id or event.get("pipeline_id") != pipeline_id:
            return None
        if event.get("level") not in ALLOWED_LEVELS:
            return None
        if event.get("event") not in ALLOWED_EVENTS:
            return None
        if event.get("step") not in ALLOWED_STEPS:
            return None
        timestamp = event.get("timestamp_utc")
        if not isinstance(timestamp, str):
            return None
        try:
            if datetime.fromisoformat(timestamp).tzinfo is None:
                return None
        except ValueError:
            return None
        events.append(event)
    if events[0].get("event") != "RUN_STARTED":
        return None
    if events[-1].get("event") != "RUN_FINISHED":
        return None
    return events


def _safe_event(raw: dict) -> dict[str, Any]:
    """Strip message and any extra/untrusted fields before reaching the agent."""
    item = {
        "event": raw["event"],
        "step": raw["step"],
        "level": raw["level"],
        "error_code": (
            raw.get("error_code") if raw.get("error_code") in ALLOWED_ERROR_CODES else None
        ),
    }
    if raw["event"] == "SCHEMA_MISMATCH" and raw.get("field") == "customer_id":
        item["field"] = "customer_id"
    return item


def _summary(events: list[dict], pipeline_id: str, run_id: str) -> dict | None:
    ending = events[-1]
    status = ending.get("status")
    scenario = ending.get("scenario")
    error_code = ending.get("error_code")
    if status not in ALLOWED_STATUSES or scenario not in ALLOWED_SCENARIOS:
        return None
    if error_code is not None and error_code not in ALLOWED_ERROR_CODES:
        return None
    counters = {}
    for name in ("records_processed", "invalid_records", "duration_ms"):
        value = ending.get(name)
        if type(value) is not int or not 0 <= value <= 1_000_000:
            return None
        counters[name] = value
    if counters["invalid_records"] > counters["records_processed"]:
        return None
    return {
        "source": "SIMULATED_LOGS",
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "timestamp_utc": ending["timestamp_utc"],
        "started_at_utc": events[0]["timestamp_utc"],
        "scenario": scenario,
        "status": status,
        **counters,
        "error_code": error_code,
        "events": [
            {"line": index, **_safe_event(event)}
            for index, event in enumerate(events, start=1)
        ],
    }


def list_simulated_runs(
    pipeline_id: str | None = None, *, directory: Path | None = None
) -> list[dict]:
    """List recent valid runs; never deserialize unbounded data."""
    if pipeline_id is not None and not is_known_pipeline(pipeline_id):
        return []
    root = directory if directory is not None else SIMULATED_LOG_DIR
    if not root.is_dir():
        return []
    try:
        # Bound the number of candidate files and skip symlinks.
        candidates = sorted(
            (p for p in root.iterdir() if p.is_file() and not p.is_symlink()),
            key=lambda p: p.stat().st_mtime_ns,
            reverse=True,
        )[:MAX_VISIBLE_RUNS * 4]
    except OSError:
        return []
    runs: list[dict] = []
    for path in candidates:
        match = re.fullmatch(r"([a-z0-9_]{3,80})__(SIM-[0-9a-f]{12})\.jsonl", path.name)
        if not match:
            continue
        file_pipeline, run_id = match.groups()
        if pipeline_id is not None and file_pipeline != pipeline_id:
            continue
        if not is_known_pipeline(file_pipeline):
            continue
        events = _read_events(path, run_id, file_pipeline)
        data = _summary(events, file_pipeline, run_id) if events else None
        if data is None:
            continue
        runs.append({key: value for key, value in data.items() if key != "events"})
        if len(runs) >= MAX_VISIBLE_RUNS:
            break
    # Start timestamps represent actual generation order; synthetic end times
    # can extend beyond the following run's start when runs occur quickly.
    return sorted(runs, key=lambda item: item["started_at_utc"], reverse=True)


def read_simulated_run(
    pipeline_id: str, run_id: str = "latest", *, directory: Path | None = None
) -> dict | None:
    """Read a specific run, or the latest valid run for this known pipeline."""
    if not is_known_pipeline(pipeline_id):
        return None
    root = directory if directory is not None else SIMULATED_LOG_DIR
    if run_id == "latest":
        runs = list_simulated_runs(pipeline_id, directory=root)
        if not runs:
            return None
        run_id = runs[0]["run_id"]
    path = _run_file(pipeline_id, run_id, root=root)
    if path is None:
        return None
    events = _read_events(path, run_id, pipeline_id)
    return _summary(events, pipeline_id, run_id) if events else None


def read_raw_messages(
    pipeline_id: str, run_id: str, *, directory: Path | None = None
) -> list[str]:
    """Dashboard only; messages NEVER enter LLM/tool-facing results."""
    root = directory if directory is not None else SIMULATED_LOG_DIR
    path = _run_file(pipeline_id, run_id, root=root)
    if path is None:
        return []
    events = _read_events(path, run_id, pipeline_id)
    if not events:
        return []
    return [
        f"{event['timestamp_utc']} | {event['level']} | {event['step']} | "
        f"{str(event.get('message', ''))[:180]}"
        for event in events
    ]
