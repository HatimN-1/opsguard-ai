"""Generate detailed, *synthetic* ADFActivityRun / ADFPipelineRun exports.

The field names are modeled on Microsoft Learn's Log Analytics schemas;
no live Azure workspace, pipeline, or account is accessed. One activity record
represents one simulated ADF activity run, not an arbitrary console log line.
Failure messages are derived from documented ADF troubleshooting examples.
"""

import json
import random
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid4, uuid5

from app.adf_monitor.source import (
    MAX_FILE_BYTES,
    MAX_LINES_PER_TABLE,
    ROOT,
    TABLES,
    _safe_table_path,
    external_workspace,
)

CASES_FILE = Path(__file__).with_name("scenarios.json")
RESOURCE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/rg-opsguard-demo/providers/"
    "Microsoft.DataFactory/factories/adf-opsguard-demo"
)
ACTIVITIES = (
    ("Lookup", "LookupSourceMetadata", "ls_onprem_sql"),
    ("GetMetadata", "InspectLandingFolder", "ls_adls_gen2"),
    ("Copy", "CopyToBronze", "ls_adls_gen2"),
    ("DataFlow", "ValidateAndNormalize", "ls_adls_gen2"),
    ("Copy", "CopyToSilver", "ls_adls_gen2"),
    ("DatabricksNotebook", "EnrichDeltaTable", "ls_azure_databricks"),
    ("ExecutePipeline", "StartDownstream", "ls_adf_orchestration"),
    ("StoredProcedure", "MergeWarehouse", "ls_synapse_sql"),
    ("WebActivity", "NotifyOperations", "ls_partner_api"),
)


def _cases() -> list[dict]:
    """Read a versioned scenario catalog, separate from diagnostic retrieval."""
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise TypeError("ADF scenario catalog must be a list")
    if not 8 <= len(cases) <= 30:
        raise ValueError("ADF scenario catalog size is invalid")
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("ADF scenario entry must be a dictionary")
        if not re.fullmatch(r"[A-Z0-9_]{2,50}", str(case.get("code", ""))):
            raise ValueError("Invalid ADF scenario error code")
    return cases


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _activity_row(
    *, pipeline_name: str, run_id: str, task_num: int,
    timestamp: datetime, failed: bool, case: dict, rng: random.Random,
) -> dict:
    activity_type, activity_label, service = ACTIVITIES[task_num % len(ACTIVITIES)]
    runtime = "AutoResolveIntegrationRuntime"
    if failed:
        activity_type = case["activity_type"]
        service = case["linked_service"]
        runtime = case["integration_runtime"]
        activity_label = "Failed" + re.sub(r"[^A-Za-z0-9]", "", activity_type)
    elif service == "ls_onprem_sql":
        runtime = "shir-demo-east"

    elapsed_ms = rng.randint(800, 15500)
    end = timestamp + timedelta(milliseconds=elapsed_ms)
    rows = rng.randint(4000, 140000)
    metrics = {
        "dataRead": rng.randint(90000, 90000000),
        "dataWritten": rng.randint(90000, 90000000),
        "rowsRead": rows,
        "rowsCopied": rows if not failed else 0,
        "copyDuration": max(1, elapsed_ms // 1000),
        "throughput": round(rng.uniform(5.5, 89.0), 2),
    } if activity_type == "Copy" else {"executionTimeMs": elapsed_ms}

    details = (
        {"errorCode": case["code"], "message": case["message"],
         "failureType": case["failure_type"]}
        if failed else {}
    )
    return {
        "TimeGenerated": end.isoformat(),
        "Start": timestamp.isoformat(),
        "End": end.isoformat(),
        "PipelineName": pipeline_name,
        "PipelineRunId": run_id,
        "ActivityRunId": str(uuid5(NAMESPACE_DNS, f"{run_id}-{task_num}")),
        "ActivityName": f"{activity_label}_{task_num:03d}",
        "ActivityType": activity_type,
        "Status": "Failed" if failed else "Succeeded",
        "Level": "Error" if failed else "Informational",
        "ErrorCode": case["code"] if failed else "",
        "ErrorMessage": case["message"] if failed else "",
        "Error": _json(details),
        "FailureType": case["failure_type"] if failed else "",
        "EffectiveIntegrationRuntime": runtime,
        "LinkedServiceName": service,
        "Output": _json(metrics if not failed else {"recordsWritten": 0}),
        "Category": "ActivityRuns",
        "OperationName": "ActivityRun",
        "SourceSystem": "Azure",  # schema-shaped synthetic value, not a real Azure event
        "SourceTable": "ADFActivityRun",
        "_ResourceId": RESOURCE_ID,
    }


def _pipeline_row(
    *, pipeline_name: str, run_id: str, start: datetime,
    end: datetime, failed: bool, case: dict,
) -> dict:
    return {
        "TimeGenerated": end.isoformat(),
        "Start": start.isoformat(),
        "End": end.isoformat(),
        "PipelineName": pipeline_name,
        "RunId": run_id,
        "Status": "Failed" if failed else "Succeeded",
        "ErrorCode": case["code"] if failed else "",
        "ErrorMessage": case["message"] if failed else "",
        "Error": _json({"errorCode": case["code"], "message": case["message"]})
        if failed else "{}",
        "FailureType": case["failure_type"] if failed else "",
        "Level": "Error" if failed else "Informational",
        "Category": "PipelineRuns",
        "OperationName": "PipelineRun",
        "SourceSystem": "Azure",  # schema-shaped synthetic value, not actual telemetry
        "SourceTable": "ADFPipelineRun",
        "_ResourceId": RESOURCE_ID,
    }


def seed_external_adf_workspace(
    *, pipelines: int = 12, runs_per_pipeline: int = 3,
    activities_per_run: int = 60, seed: int = 21,
    root: Path | None = None, reset: bool = False,
) -> dict:
    """Write many correlated activity runs and pipeline runs outside Git.

    Reset truncates ONLY the two fixed ADF table files in the configured
    external directory, never an arbitrary path or directory tree.
    """
    if not 1 <= pipelines <= 30:
        raise ValueError("pipelines must be in 1..30")
    if not 1 <= runs_per_pipeline <= 10:
        raise ValueError("runs_per_pipeline must be in 1..10")
    if not 10 <= activities_per_run <= 200:
        raise ValueError("activities_per_run must be in 10..200")
    target = (root if root is not None else external_workspace()).resolve()
    if target == ROOT or ROOT in target.parents:
        raise ValueError("The ADF demo workspace must be outside the repository")
    target.mkdir(parents=True, exist_ok=True)
    paths = {name: _safe_table_path(target, name) for name in TABLES}
    rng = random.Random(seed)
    started = datetime.now(UTC)
    payload: dict[str, list[dict]] = {name: [] for name in TABLES}
    prefix = uuid4().hex[:8]
    cases = _cases()

    for index in range(pipelines):
        domain = ("orders", "customers", "payments", "inventory")[index % 4]
        pipeline_name = f"adf_{index + 1:02d}_{domain}"
        for run_idx in range(runs_per_pipeline):
            run_id = str(uuid5(NAMESPACE_DNS, f"{prefix}-{index + 1}-{run_idx + 1}"))
            start = started - timedelta(hours=1 + run_idx * 3, minutes=index)
            case = cases[(index + run_idx) % len(cases)]
            failed = (index + run_idx) % 4 != 0 or case["code"] == "3202"
            bad_activity = rng.randint(5, activities_per_run - 2) if failed else None
            last_end = start
            for task_num in range(activities_per_run):
                task_start = start + timedelta(seconds=task_num * 4)
                activity = _activity_row(
                    pipeline_name=pipeline_name, run_id=run_id,
                    task_num=task_num, timestamp=task_start,
                    failed=task_num == bad_activity, case=case, rng=rng,
                )
                payload["ADFActivityRun"].append(activity)
                last_end = max(last_end, datetime.fromisoformat(activity["End"]))
            payload["ADFPipelineRun"].append(_pipeline_row(
                pipeline_name=pipeline_name, run_id=run_id,
                start=start, end=last_end + timedelta(milliseconds=100),
                failed=failed, case=case,
            ))

    lines = {
        table: [_json(item) + "\n" for item in rows]
        for table, rows in payload.items()
    }
    # Ensure that a failed preflight does not partially write one table.
    for table, path in paths.items():
        size = sum(len(line.encode("utf-8")) for line in lines[table])
        current = 0 if reset or not path.exists() else path.stat().st_size
        if size + current > MAX_FILE_BYTES:
            raise ValueError("Generated ADF logs exceed the safe workspace size")
        if len(lines[table]) > MAX_LINES_PER_TABLE:
            raise ValueError("Generated ADF logs exceed the safe line limit")
    for table, path in paths.items():
        # Files are fixed names, symlinks were rejected by _safe_table_path.
        with path.open("w" if reset else "a", encoding="utf-8") as handle:
            handle.writelines(lines[table])

    return {
        "source": "EXTERNAL_ADF_SYNTHETIC_JSONL",
        "workspace_dir": str(target),
        "simulation": True,
        "pipelines": pipelines,
        "runs": pipelines * runs_per_pipeline,
        "activity_events": len(payload["ADFActivityRun"]),
        "pipeline_events": len(payload["ADFPipelineRun"]),
        "scenarios_available": len(cases),
        "reset": reset,
    }
