"""Read-only Azure Data Factory log source: external JSONL or Azure Log Analytics.

External JSONL is a *synthetic ADF-shaped export* stored OUTSIDE this repository.
Azure mode needs explicit configuration and optional Azure SDK dependencies.
Neither mode reads arbitrary paths supplied by a language model.
"""

import json
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE = ROOT.parent / "opsguard-adf-external-workspace"
TABLES = ("ADFPipelineRun", "ADFActivityRun")
PIPELINE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,79}\Z")
RUN_RE = re.compile(r"[A-Za-z0-9_.:-]{1,100}\Z")
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_LINES_PER_TABLE = 25000
ALLOWED_FIELDS = {
    "TimeGenerated", "PipelineName", "RunId", "PipelineRunId", "ActivityName",
    "ActivityType", "Status", "ErrorCode", "ErrorMessage", "FailureType", "Level",
    "SourceTable",
}


class SourceUnavailable(Exception):
    """A source is absent, unavailable or cannot be safely accessed."""


def external_workspace() -> Path:
    return Path(os.getenv("OPSGUARD_ADF_EXTERNAL_DIR", str(DEFAULT_WORKSPACE))).expanduser()


def source_mode() -> str:
    mode = os.getenv("OPSGUARD_ADF_SOURCE", "external_demo")
    if mode not in {"external_demo", "azure"}:
        raise SourceUnavailable("Configuration de source ADF inconnue")
    return mode


def _safe_table_path(root: Path, table: str) -> Path:
    if table not in TABLES:
        raise SourceUnavailable("Table non autorisée")
    root = root.resolve()
    path = root / f"{table}.jsonl"
    if path.is_symlink() or path.resolve().parent != root:
        raise SourceUnavailable("Chemin de journal non autorisé")
    if path.exists() and path.stat().st_size > MAX_FILE_BYTES:
        raise SourceUnavailable("Journal trop volumineux")
    return path


def _safe_text(value: object, maxlen: int) -> str:
    return value[:maxlen] if isinstance(value, str) else ""


def _safe_identifier(value: object, maxlen: int) -> str:
    """Keep only metadata IDs; arbitrary log text must not enter LLM context."""
    if not isinstance(value, str) or not 1 <= len(value) <= maxlen:
        return ""
    return value if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value) else ""


def _safe_copy_metrics(raw_output: object) -> dict[str, int]:
    """Extract only nonnegative numeric Copy counters; discard arbitrary output."""
    if not isinstance(raw_output, (str, dict)):
        return {}
    try:
        output = json.loads(raw_output[:3000]) if isinstance(raw_output, str) else raw_output
    except json.JSONDecodeError:
        return {}
    if not isinstance(output, dict):
        return {}
    fields = ("rowsRead", "rowsCopied", "dataRead", "dataWritten", "copyDuration")
    result: dict[str, int] = {}
    for key in fields:
        value = output.get(key)
        if type(value) is int and 0 <= value <= 10**12:
            result[key] = value
    return result


def _normalize(raw: object, table: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = _safe_text(raw.get("PipelineName"), 80)
    run_id = _safe_text(raw.get("PipelineRunId") or raw.get("RunId"), 100)
    timestamp = _safe_text(raw.get("TimeGenerated"), 45)
    if not PIPELINE_RE.fullmatch(name) or not RUN_RE.fullmatch(run_id):
        return None
    try:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            return None
    except ValueError:
        return None
    status = _safe_text(raw.get("Status"), 32)
    if status not in {"Succeeded", "Failed", "InProgress", "Cancelled", "Queued"}:
        return None
    # Strictly whitelist metadata; do not allow arbitrary log messages or
    # input/output/connection strings into model evidence.
    code = _safe_text(raw.get("ErrorCode"), 80)
    if code and not re.fullmatch(r"[A-Za-z0-9_]{1,80}", code):
        code = ""
    activity_name = _safe_identifier(raw.get("ActivityName"), 80)
    activity_id = _safe_identifier(raw.get("ActivityRunId"), 100)
    activity_type = _safe_identifier(raw.get("ActivityType"), 50)
    runtime = _safe_identifier(raw.get("EffectiveIntegrationRuntime"), 80)
    service = _safe_identifier(raw.get("LinkedServiceName"), 80)
    failure = _safe_text(raw.get("FailureType"), 20)
    if failure not in {"UserError", "SystemError", "Unknown", ""}:
        failure = ""
    return {
        "timestamp_utc": dt.astimezone(UTC).isoformat(),
        "pipeline_name": name,
        "run_id": run_id,
        "table": table,
        "activity_run_id": activity_id,
        "activity_name": activity_name,
        "activity_type": activity_type,
        "integration_runtime": runtime,
        "linked_service": service,
        "failure_type": failure,
        "copy_metrics": _safe_copy_metrics(raw.get("Output")) if table == "ADFActivityRun" else {},
        "status": status,
        "error_code": code or None,
        "level": _safe_text(raw.get("Level"), 20),
        # Never expose ErrorMessage/Error/Input/raw Output to the agent.
    }


def _read_external(root: Path) -> list[dict]:
    rows = []
    for table in TABLES:
        path = _safe_table_path(root, table)
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as handle:
            for line_num, line in enumerate(handle, 1):
                if line_num > MAX_LINES_PER_TABLE:
                    raise SourceUnavailable("Limite de lignes dépassée")
                if len(line) > 8000:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                normalized = _normalize(record, table)
                if normalized:
                    rows.append(normalized)
    return rows


def _kql_pipeline_filter(pipeline_name: str | None) -> str:
    if pipeline_name:
        # Restrictive ID validation is the first and strongest KQL injection gate.
        if not PIPELINE_RE.fullmatch(pipeline_name):
            raise ValueError("Invalid pipeline name")
        return f"| where PipelineName == {json.dumps(pipeline_name)}"
    return ""


def build_kql(pipeline_name: str | None, limit: int) -> str:
    """Generate a bounded read-only query over resource-specific ADF tables."""
    if not 1 <= limit <= 500:
        raise ValueError("Invalid limit")
    condition = _kql_pipeline_filter(pipeline_name)
    return (
        "union isfuzzy=true "
        "(ADFPipelineRun " + condition + " | project TimeGenerated, PipelineName, "
        "RunId, ActivityName='', ActivityType='', Status, ErrorCode, "
        "Level, SourceTable='ADFPipelineRun'), "
        "(ADFActivityRun " + condition + " | project TimeGenerated, PipelineName, "
        "RunId=PipelineRunId, ActivityName, ActivityType, Status, ErrorCode, "
        "Level, SourceTable='ADFActivityRun') "
        f"| top {limit} by TimeGenerated desc"
    )


def _read_azure(pipeline_name: str | None, hours: int, limit: int) -> list[dict]:
    workspace = os.getenv("OPSGUARD_ADF_WORKSPACE_ID", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", workspace):
        raise SourceUnavailable("Configurer OPSGUARD_ADF_WORKSPACE_ID (GUID)")
    try:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.query import LogsQueryClient, LogsQueryStatus
    except ImportError as exc:
        raise SourceUnavailable(
            "Installer requirements-azure-optional.txt pour le mode Azure"
        ) from exc
    client = LogsQueryClient(DefaultAzureCredential())
    try:
        response = client.query_workspace(
            workspace,
            build_kql(pipeline_name, limit),
            timespan=timedelta(hours=hours),
        )
        if response.status != LogsQueryStatus.SUCCESS:
            raise SourceUnavailable("Résultat Azure partiel ou indisponible")
        rows: list[dict] = []
        for table in response.tables:
            names = [getattr(c, "name", c) for c in table.columns]
            for values in table.rows:
                raw = dict(zip(names, values, strict=True))
                kind = raw.get("SourceTable")
                if kind not in TABLES:
                    continue
                # SDK may return Python datetime objects.
                if isinstance(raw.get("TimeGenerated"), datetime):
                    raw["TimeGenerated"] = raw["TimeGenerated"].isoformat()
                normalized = _normalize(raw, kind)
                if normalized:
                    rows.append(normalized)
        return rows
    except SourceUnavailable:
        raise
    except Exception as exc:
        # Do not reveal workspace IDs, auth errors or service details to LLM/UI.
        raise SourceUnavailable("Requête Azure indisponible (accès/permissions/réseau)") from exc


def query_adf_logs(
    pipeline_name: str | None = None,
    *,
    run_id: str | None = None,
    hours: int = 72,
    limit: int = 200,
    error_codes: list[str] | None = None,
    excluded_error_codes: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """Read bounded, normalized and sanitized evidence from chosen source."""
    if pipeline_name is not None and not PIPELINE_RE.fullmatch(pipeline_name):
        raise ValueError("Invalid pipeline name")
    if run_id is not None and not RUN_RE.fullmatch(run_id):
        raise ValueError("Invalid run id")
    if not 1 <= hours <= 720 or not 1 <= limit <= 500:
        raise ValueError("Invalid query bounds")
    for codes in (error_codes, excluded_error_codes):
        if codes is not None and (
            not isinstance(codes, list) or len(codes) > 10
            or any(not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", code)
                   for code in codes)
        ):
            raise ValueError("Invalid error code filter")
    mode = source_mode()
    records = (
        _read_external(root or external_workspace())
        if mode == "external_demo"
        else _read_azure(pipeline_name, hours, limit)
    )
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    matching = [
        row for row in records
        if datetime.fromisoformat(row["timestamp_utc"]) >= cutoff
        and (pipeline_name is None or row["pipeline_name"] == pipeline_name)
        and (run_id is None or row["run_id"] == run_id)
        and (error_codes is None or row.get("error_code") in error_codes)
        and (excluded_error_codes is None or row.get("error_code") not in excluded_error_codes)
    ]
    matching.sort(key=lambda item: item["timestamp_utc"], reverse=True)
    included = matching[:limit]
    errors = Counter(
        (row["error_code"], row["pipeline_name"], row["run_id"])
        for row in matching if row["error_code"]
    )
    evidence_events = [
        row for row in matching if row.get("error_code")
    ][:12]
    activity_names_by_error: dict[tuple[str, str, str], list[str]] = {}
    for row in matching:
        if (row["table"] != "ADFActivityRun" or row["status"] != "Failed"
                or not row.get("error_code") or not row.get("activity_name")):
            continue
        marker = (row["error_code"], row["pipeline_name"], row["run_id"])
        activities = activity_names_by_error.setdefault(marker, [])
        if row["activity_name"] not in activities and len(activities) < 5:
            activities.append(row["activity_name"])
    errors_list = [
        {
            "error_code": code, "pipeline_name": name, "run_id": rid,
            "occurrences": n,
            "failing_activities": activity_names_by_error.get((code, name, rid), []),
        }
        for (code, name, rid), n in errors.most_common(15)
    ]
    status_counts = dict(Counter(row["status"] for row in matching))
    pipeline_names = sorted({row["pipeline_name"] for row in matching})
    activity_rows = [row for row in matching if row["table"] == "ADFActivityRun"]
    pipeline_rows = [row for row in matching if row["table"] == "ADFPipelineRun"]
    pipeline_status_counts = dict(Counter(row["status"] for row in pipeline_rows))
    # Run metadata is produced from the full filtered export, never the UI's
    # 500-event display limit. Each pipeline parent is counted only once.
    seen_run_ids: set[tuple[str, str]] = set()
    run_records: list[dict] = []
    for row in pipeline_rows:
        key = (row["pipeline_name"], row["run_id"])
        if key in seen_run_ids:
            continue
        seen_run_ids.add(key)
        run_records.append({
            "pipeline_name": row["pipeline_name"],
            "run_id": row["run_id"],
            "status": row["status"],
            "timestamp_utc": row["timestamp_utc"],
            "error_code": row["error_code"],
        })
    latest_by_pipeline: dict[str, dict] = {}
    for row in run_records:
        latest_by_pipeline.setdefault(row["pipeline_name"], row)
    activity_status_counts = dict(Counter(row["status"] for row in activity_rows))
    unique_pipeline_runs = {(row["pipeline_name"], row["run_id"]) for row in pipeline_rows}
    failed_pipeline_runs = {
        (row["pipeline_name"], row["run_id"])
        for row in pipeline_rows if row["status"] == "Failed"
    }
    copy_rows = [row for row in activity_rows if row["activity_type"] == "Copy"]
    totals = {
        key: sum(row["copy_metrics"].get(key, 0) for row in copy_rows)
        for key in ("rowsRead", "rowsCopied", "dataRead", "dataWritten")
    }
    return {
        "source": "AZURE_LOG_ANALYTICS" if mode == "azure" else "EXTERNAL_ADF_SYNTHETIC_JSONL",
        "simulation": mode != "azure",
        "pipeline_name": pipeline_name,
        "run_id": run_id,
        "lookback_hours": hours,
        "matching_events": len(matching),
        "returned_events": len(included),
        "truncated": len(matching) > limit or (mode == "azure" and len(matching) >= limit),
        "coverage": "SAMPLED_UP_TO_LIMIT" if mode == "azure" else "COMPLETE_FILTERED_EXPORT",
        "pipeline_names": pipeline_names[:60],
        "requested_error_codes": list(error_codes) if error_codes is not None else None,
        "excluded_error_codes": list(excluded_error_codes or []),
        "run_records": run_records[:200],
        "latest_pipeline_runs": list(latest_by_pipeline.values()),
        "status_counts": status_counts,
        "pipeline_status_counts": pipeline_status_counts,
        "activity_status_counts": activity_status_counts,
        "distinct_pipeline_run_count": len(unique_pipeline_runs),
        "failed_pipeline_run_count": len(failed_pipeline_runs),
        "pipeline_run_count": len(pipeline_rows),
        "activity_run_count": len(activity_rows),
        "activity_types": dict(Counter(row["activity_type"] for row in activity_rows)),
        "copy_metrics_total": totals,
        "errors": errors_list,
        "evidence_events": evidence_events,
        "events": included,
    }


def known_external_pipelines(root: Path | None = None) -> list[str]:
    """Discover pipeline names from a configured external export; no LLM paths."""
    if source_mode() != "external_demo":
        return []
    rows = _read_external(root or external_workspace())
    return sorted({row["pipeline_name"] for row in rows})[:100]
