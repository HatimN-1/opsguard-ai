"""Audit trace quality AFTER the existing fresh-trace marker (read-only logs).

The audit never prints or exports prompts, responses, run IDs or tool arguments.
Exit status: 0 = PASS, 1 = FAIL, 2 = INCONCLUSIVE.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SELECTION_FIELDS = (
    "selection_source", "selection_reason", "selection_category",
    "tool_selection_reason", "tool_selection_source", "source", "reason",
)
DURATION_FIELDS = ("duration_ms", "latency_ms", "elapsed_ms", "tool_duration_ms")
# These names refer to content that should not be stored in *operational* traces.
FORBIDDEN_KEYS = {
    "prompt", "system_prompt", "user_prompt", "user_question", "question",
    "messages", "conversation", "chain_of_thought", "reasoning_content",
    "thoughts", "raw_response", "llm_response", "response_text", "llm_summary",
    "answer", "full_response", "raw_payload", "request_body", "response_body",
    "password", "passwd", "secret", "api_key", "apikey", "access_token",
    "refresh_token", "authorization", "credentials", "cookie", "headers",
    "private_key", "client_secret", "connection_string", "raw_tool_result",
    "tool_result", "raw_output", "raw_text", "user_input", "user_message",
    "chat_history", "tool_args_raw", "tool_arguments_raw", "final_answer",
}
# Values are inspected in memory but NEVER included in output.
SECRET_PATTERNS = (
    re.compile(r"\bbearer\s+[a-z0-9._~+/-]{10,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|sk-proj)-[a-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|password|client[_-]?secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:[?&]sig=|AccountKey=|SharedAccessSignature=)\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"[A-Z]:\\Users\\[^\\\s]+\\", re.IGNORECASE),
)
TERMINALS = {"AGENT_COMPLETED", "AGENT_FAILED", "LIMIT_REACHED"}


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _number(obj: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = obj.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        ):
            return float(value)
    return None


def _selection(obj: dict[str, Any]) -> str | None:
    for key in SELECTION_FIELDS:
        if isinstance(obj.get(key), str) and obj[key].strip():
            return key
    return None


def _privacy_findings(obj: Any) -> Counter[str]:
    """Inspect recursively, count concerns, and discard all original values."""
    found: Counter[str] = Counter()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                found["SENSITIVE_FIELD_NAME"] += 1
            found.update(_privacy_findings(value))
    elif isinstance(obj, list):
        for value in obj:
            found.update(_privacy_findings(value))
    elif isinstance(obj, str) and any(
        pattern.search(obj) for pattern in SECRET_PATTERNS
    ):
        found["POSSIBLE_SECRET_OR_PERSONAL_DATA"] += 1
    return found


def audit_record(record: dict[str, Any]) -> tuple[Counter[str], Counter[str], Counter[str]]:
    errors: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    metrics: Counter[str] = Counter()

    privacy = _privacy_findings(record)
    errors.update(privacy)
    if not isinstance(record.get("trace_id"), str) or not record["trace_id"].strip():
        errors["TRACE_ID_MISSING"] += 1
    final_time = _datetime(record.get("timestamp_utc"))
    if final_time is None:
        errors["TRACE_TIMESTAMP_INVALID"] += 1
    latency = _number(record, ("latency_ms",))
    if latency is None:
        errors["TRACE_LATENCY_INVALID"] += 1

    events = record.get("events")
    if not isinstance(events, list) or not events:
        errors["TIMELINE_MISSING"] += 1
        return errors, warnings, metrics
    if type(record.get("event_count")) is int and record["event_count"] != len(events):
        errors["EVENT_COUNT_MISMATCH"] += 1

    pending: dict[str, deque[tuple[int, datetime | None]]] = defaultdict(deque)
    req_count = completed_count = 0
    last_timestamp: datetime | None = None
    kinds: set[str] = set()
    durations: list[float] = []

    for event in events:
        if not isinstance(event, dict):
            errors["EVENT_NOT_OBJECT"] += 1
            continue
        kind = event.get("event_type")
        if not isinstance(kind, str):
            errors["EVENT_TYPE_MISSING"] += 1
            continue
        kinds.add(kind)
        timestamp = _datetime(event.get("timestamp_utc"))
        if timestamp is None:
            errors["EVENT_TIMESTAMP_INVALID"] += 1
        else:
            if last_timestamp is not None and timestamp < last_timestamp - timedelta(seconds=2):
                errors["EVENTS_OUT_OF_ORDER"] += 1
            last_timestamp = timestamp
            if final_time is not None and timestamp > final_time + timedelta(seconds=5):
                errors["EVENT_AFTER_TRACE_COMPLETION"] += 1
        if kind == "TOOL_REQUESTED":
            req_count += 1
            tool = event.get("tool")
            if not isinstance(tool, str) or not tool.strip():
                errors["TOOL_NAME_MISSING"] += 1
                tool = "__missing_tool__"
            selection_field = _selection(event)
            if selection_field is None:
                errors["TOOL_SELECTION_UNDOCUMENTED"] += 1
            elif selection_field in {"reason", "source"}:
                warnings["GENERIC_SELECTION_FIELD"] += 1
            pending[tool].append((event.get("step", -1), timestamp))
        elif kind == "TOOL_COMPLETED":
            completed_count += 1
            tool = event.get("tool")
            if not isinstance(tool, str) or not tool.strip():
                errors["TOOL_NAME_MISSING"] += 1
                tool = "__missing_tool__"
            duration = _number(event, DURATION_FIELDS)
            if duration is None:
                errors["TOOL_DURATION_MISSING_OR_INVALID"] += 1
            else:
                durations.append(duration)
            if not isinstance(event.get("ok"), bool):
                errors["TOOL_RESULT_STATUS_MISSING"] += 1
            elif event["ok"] is False and not event.get("error"):
                warnings["TOOL_ERROR_CATEGORY_MISSING"] += 1
            if not pending[tool]:
                errors["TOOL_COMPLETED_WITHOUT_REQUEST"] += 1
            else:
                request_step, request_time = pending[tool].popleft()
                completion_step = event.get("step", -1)
                if (isinstance(request_step, int) and request_step >= 1
                        and isinstance(completion_step, int) and completion_step >= 1
                        and request_step != completion_step):
                    warnings["TOOL_STEP_DIFFERENT"] += 1
                if request_time is not None and timestamp is not None:
                    if timestamp < request_time - timedelta(seconds=2):
                        errors["TOOL_FINISHED_BEFORE_REQUEST"] += 1
                    elif duration is not None:
                        wall_time_ms = (timestamp - request_time).total_seconds() * 1000
                        if abs(wall_time_ms - duration) > max(3000.0, wall_time_ms * 0.6):
                            warnings["TOOL_DURATION_WALL_CLOCK_DIFFERENCE"] += 1

    metrics["tool_requested"] = req_count
    metrics["tool_completed"] = completed_count
    metrics["events"] = len(events)
    unpaired = sum(len(queue) for queue in pending.values())
    if unpaired:
        errors["TOOL_REQUEST_WITHOUT_COMPLETION"] += unpaired
    if req_count != completed_count:
        errors["TOOL_CALL_PAIR_COUNT_MISMATCH"] += 1
    if type(record.get("tool_call_count")) is not int:
        errors["TRACE_TOOL_COUNT_MISSING"] += 1
    elif record["tool_call_count"] != req_count:
        errors["TRACE_TOOL_COUNT_MISMATCH"] += 1
    if not kinds.intersection(TERMINALS):
        warnings["TERMINAL_AGENT_EVENT_NOT_SEEN"] += 1
    if latency is not None and durations and max(durations) > latency + 3000:
        warnings["TOOL_DURATION_EXCEEDS_TRACE_LATENCY"] += 1
    if "AGENT_STARTED" not in kinds:
        warnings["START_EVENT_NOT_SEEN"] += 1
    return errors, warnings, metrics


def audit_file(source: Path, marker: Path) -> tuple[int, dict[str, Any]]:
    report: dict[str, Any] = {
        "audit": "fresh_trace_quality_v1", "scope": "new_records_after_existing_marker",
        "result": "INCONCLUSIVE", "records_checked": 0,
        "metrics": {}, "errors": {}, "warnings": {}, "sample_positions": [],
        "note": "Only categories and line numbers; no prompts, Run IDs, responses, or arguments.",
    }
    if not source.is_file() or not marker.is_file():
        report["inconclusive_reason"] = "SOURCE_OR_MARKER_MISSING"
        return 2, report
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        line_baseline = metadata["lines"]
        size_baseline = metadata["size_bytes"]
        if (type(line_baseline) is not int or line_baseline < 0
                or type(size_baseline) is not int or size_baseline < 0):
            raise ValueError("invalid marker")
    except (OSError, ValueError, TypeError, KeyError):
        report["inconclusive_reason"] = "MARKER_INVALID"
        return 2, report
    if source.stat().st_size < size_baseline:
        report["inconclusive_reason"] = "LOG_TRUNCATED_SINCE_MARK"
        return 2, report

    total_errors: Counter[str] = Counter()
    total_warnings: Counter[str] = Counter()
    total_metrics: Counter[str] = Counter()
    seen_ids: set[str] = set()
    checked = 0
    with source.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if line_number <= line_baseline:
                continue
            checked += 1
            if not line.strip():
                total_errors["EMPTY_LINE"] += 1
                continue
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                total_errors["INVALID_JSON"] += 1
                continue
            if not isinstance(record, dict):
                total_errors["TRACE_NOT_OBJECT"] += 1
                continue
            trace_id = record.get("trace_id")
            if isinstance(trace_id, str):
                if trace_id in seen_ids:
                    total_errors["DUPLICATE_TRACE_ID"] += 1
                seen_ids.add(trace_id)
            errors, warnings, metrics = audit_record(record)
            total_errors.update(errors)
            total_warnings.update(warnings)
            total_metrics.update(metrics)
            if (errors or warnings) and len(report["sample_positions"]) < 12:
                report["sample_positions"].append({
                    "line": line_number,
                    "error_categories": sorted(errors),
                    "warning_categories": sorted(warnings),
                })

    report["records_checked"] = checked
    report["metrics"] = dict(sorted(total_metrics.items()))
    report["errors"] = dict(sorted(total_errors.items()))
    report["warnings"] = dict(sorted(total_warnings.items()))
    if checked == 0:
        report["inconclusive_reason"] = "NO_NEW_TRACE_ROWS"
        return 2, report
    if total_metrics["tool_requested"] == 0 and not total_errors:
        report["inconclusive_reason"] = "NO_NEW_TOOL_INTERACTION"
        return 2, report
    report["result"] = "FAIL" if total_errors else "PASS_WITH_WARNINGS" if total_warnings else "PASS"
    return (1 if total_errors else 0), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("logs/agent_traces.jsonl"))
    parser.add_argument("--marker", type=Path, default=Path("outputs/fresh_trace_probe_marker.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/fresh_trace_quality_audit.json"))
    args = parser.parse_args()
    code, report = audit_file(args.source, args.marker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("OpsGuard — ETAPE 1B : audit QUALITE des traces recentes (lecture seule)")
    print("  Lignes inspectees :", report["records_checked"])
    for name, count in report["metrics"].items():
        print(f"  {name}: {count}")
    for category, count in report["errors"].items():
        print(f"  ECHEC {category}: {count}")
    for category, count in report["warnings"].items():
        print(f"  NOTE {category}: {count}")
    if report.get("inconclusive_reason"):
        print("  INCONCLUSIF:", report["inconclusive_reason"])
    print("  RESULTAT:", report["result"])
    print("  Rapport anonyme:", args.output)
    print("  Aucun contenu brut de trace n'a ete affiche ni copie dans le rapport.")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
