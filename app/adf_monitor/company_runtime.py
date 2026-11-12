"""Append synthetic Azure Data Factory executions for the FIXED company assets.

This module cannot add, rename, remove, or execute a real ADF pipeline.
It writes new ADF-shaped diagnostic events to a separate demo workspace.
"""

import json
import random
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.adf_monitor.business_catalog import known_business_ids, require_business_pipeline
from app.adf_monitor.seed import _activity_row, _cases, _pipeline_row
from app.adf_monitor.source import (
    MAX_FILE_BYTES,
    MAX_LINES_PER_TABLE,
    ROOT,
    TABLES,
    _safe_table_path,
    external_workspace,
    source_mode,
)

_LOCK = threading.RLock()


def available_scenarios() -> list[str]:
    return ["RANDOM", "SUCCESS", *[item["code"] for item in _cases()]]


def _preflight(workspace: Path, additions: dict[str, list[str]]) -> dict[str, Path]:
    paths = {table: _safe_table_path(workspace, table) for table in TABLES}
    for table, path in paths.items():
        count = 0
        if path.exists():
            with path.open(encoding="utf-8") as file:
                count = sum(1 for _ in file)
        if count + len(additions[table]) > MAX_LINES_PER_TABLE:
            raise ValueError(
                "Workspace retention limit reached; archive old logs before continuing"
            )
        size = path.stat().st_size if path.exists() else 0
        size += sum(len(line.encode("utf-8")) for line in additions[table])
        if size > MAX_FILE_BYTES:
            raise ValueError("Workspace size limit reached; archive old logs before continuing")
    return paths


def append_business_run(
    pipeline_id: str, *, scenario: str = "RANDOM", activities: int = 90,
    seed: int | None = None, root: Path | None = None,
) -> dict:
    """Append one new run; never change the twelve-company-pipeline catalog.

    Each activity event is a synthetic execution record, not an arbitrary
    console line. Repeated workflow stages represent batch/partition iterations.
    """
    if source_mode() != "external_demo":
        raise ValueError("This fixed-company demo does not connect to Azure")
    pipeline = require_business_pipeline(pipeline_id)
    if not 18 <= activities <= 150:
        raise ValueError("Activity count must be between 18 and 150")
    cases = {case["code"]: case for case in _cases()}
    if scenario not in ("SUCCESS", "RANDOM", *cases):
        raise ValueError("Unknown scenario")
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    if scenario == "RANDOM":
        scenario = rng.choice(["SUCCESS", "SUCCESS", *cases])
    case = cases.get(scenario) or cases["2003"]
    failed = scenario != "SUCCESS"
    workspace = (root or external_workspace()).resolve()
    if workspace == ROOT or ROOT in workspace.parents:
        raise ValueError("Log source must be external to the project")
    workflow = pipeline["workflow"]
    run_id = str(uuid4())
    # Recorded execution appears to have just finished; only the simulation
    # process is instantaneous. We never claim a real ETL was run.
    start = datetime.now(UTC) - timedelta(seconds=activities * 6 + 30)
    candidates = [
        i for i in range(8, activities - 2)
        if workflow[i % len(workflow)]["activity_type"] == case["activity_type"]
    ]
    exact = [
        i for i in candidates
        if workflow[i % len(workflow)]["linked_service"] == case["linked_service"]
    ]
    failure_index = rng.choice(exact or candidates) if failed and candidates else None
    if failed and failure_index is None:
        raise ValueError("Failure scenario incompatible with the fixed workflow")

    activity_rows = []
    last_end = start
    for index in range(activities):
        stage = workflow[index % len(workflow)]
        event = _activity_row(
            pipeline_name=pipeline_id,
            run_id=run_id,
            task_num=index,
            timestamp=start + timedelta(seconds=index * 6),
            failed=index == failure_index,
            case=case,
            rng=rng,
        )
        # Preserve the company's fixed workflow rather than invent new tasks.
        event["ActivityName"] = f"{stage['name']}_Batch_{index // len(workflow) + 1:03d}"
        event["ActivityType"] = stage["activity_type"]
        event["LinkedServiceName"] = stage["linked_service"]
        event["EffectiveIntegrationRuntime"] = stage["integration_runtime"]
        event["SourceSystem"] = "SyntheticADF"
        activity_rows.append(event)
        last_end = max(last_end, datetime.fromisoformat(event["End"]))
    parent = _pipeline_row(
        pipeline_name=pipeline_id, run_id=run_id,
        start=start, end=last_end + timedelta(milliseconds=100),
        failed=failed, case=case,
    )
    parent["SourceSystem"] = "SyntheticADF"
    additions = {
        "ADFPipelineRun": [json.dumps(parent, ensure_ascii=False) + "\n"],
        "ADFActivityRun": [json.dumps(item, ensure_ascii=False) + "\n" for item in activity_rows],
    }
    with _LOCK:
        workspace.mkdir(parents=True, exist_ok=True)
        paths = _preflight(workspace, additions)
        # The lock protects concurrent Streamlit sessions in one process.
        # CLI processes should not write concurrently to the same workspace.
        for table in TABLES:
            with paths[table].open("a", encoding="utf-8") as file:
                file.writelines(additions[table])
    return {
        "source": "EXTERNAL_ADF_SYNTHETIC_JSONL",
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "scenario": scenario,
        "status": "Failed" if failed else "Succeeded",
        "activity_events": len(activity_rows),
        "pipeline_events": 1,
        "workspace": str(workspace),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }


def append_company_shift(*, activities: int = 90, seed: int | None = None) -> list[dict]:
    """Append one additional simulated execution for each of the 12 fixed pipelines."""
    return [
        append_business_run(pid, activities=activities,
                            seed=None if seed is None else seed + idx)
        for idx, pid in enumerate(known_business_ids())
    ]
