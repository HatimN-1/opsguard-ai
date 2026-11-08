
"""Read simulated ETL pipeline statuses (no production connection)."""

import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "pipelines.json"


def get_pipeline_status(pipeline_id: str) -> dict | None:
    """Return one pipeline's status, or None if it does not exist."""
    with DATA_FILE.open(encoding="utf-8") as handle:
        pipelines = json.load(handle)

    for pipeline in pipelines:
        if pipeline["pipeline_id"] == pipeline_id:
            return pipeline

    return None
