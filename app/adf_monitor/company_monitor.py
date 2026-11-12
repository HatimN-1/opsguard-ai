"""Read-only operational views for the twelve fixed-company pipelines."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.adf_monitor.business_catalog import known_business_ids, require_business_pipeline
from app.adf_monitor.source import (
    _read_external,
    external_workspace,
    source_mode,
)


def list_business_runs(*, hours: int = 168, root: Path | None = None) -> list[dict]:
    """Return one row per pipeline run; activity and pipeline failures aren't double counted."""
    if source_mode() != "external_demo":
        raise ValueError("Business mode is external synthetic logs only")
    if not 1 <= hours <= 720:
        raise ValueError("Invalid time window")
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    allowed = set(known_business_ids())
    rows = [
        row for row in _read_external(root or external_workspace())
        if row["table"] == "ADFPipelineRun"
        and row["pipeline_name"] in allowed
        and datetime.fromisoformat(row["timestamp_utc"]) >= cutoff
    ]
    rows.sort(key=lambda row: row["timestamp_utc"], reverse=True)
    # Each RunId is immutable within the generated demo, protect against duplicate rows.
    seen = set()
    unique = []
    for row in rows:
        key = (row["pipeline_name"], row["run_id"])
        if key not in seen:
            unique.append(row)
            seen.add(key)
    return unique


def company_snapshot(*, hours: int = 168, root: Path | None = None) -> dict:
    runs = list_business_runs(hours=hours, root=root)
    latest = {}
    for row in runs:
        latest.setdefault(row["pipeline_name"], row)
    pipelines = []
    for pid in known_business_ids():
        metadata = require_business_pipeline(pid)
        current = latest.get(pid)
        pipelines.append({
            "pipeline_id": pid,
            "display_name": metadata["display_name"],
            "domain": metadata["domain"],
            "owner_team": metadata["owner_team"],
            "criticality": metadata["criticality"],
            "last_status": current["status"] if current else "NO_TELEMETRY",
            "last_run_id": current["run_id"] if current else None,
            "last_seen_utc": current["timestamp_utc"] if current else None,
        })
    return {
        "company_pipeline_count": 12,
        "observed_pipeline_count": len(latest),
        "total_runs_in_window": len(runs),
        "failed_runs_in_window": sum(x["status"] == "Failed" for x in runs),
        "latest_failed_pipelines": sum(x["last_status"] == "Failed" for x in pipelines),
        "pipelines": pipelines,
        "runs": runs,
    }
