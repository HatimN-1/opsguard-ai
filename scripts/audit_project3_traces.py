"""Audit operational JSONL traces without exporting prompts, run IDs or model text.

Usage: python -m scripts.audit_project3_traces --check
Only validates the audit trail actually present, not semantic model correctness.
Old traces without an event timeline are counted separately (legacy coverage).
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACES = ROOT / "logs" / "agent_traces.jsonl"
DEFAULT_OUTPUT = ROOT / "outputs" / "project3_trace_audit.json"
EVENT_TYPES = {
    "AGENT_STARTED", "LLM_REQUESTED", "LLM_RESPONDED", "TOOL_REQUESTED",
    "TOOL_COMPLETED", "AGENT_COMPLETED", "AGENT_FAILED", "LIMIT_REACHED",
    "REQUEST_REJECTED", "ESCALATION_PROPOSED",
}
ALLOWED_SAFE_ARGUMENTS = {
    "pipeline_id", "run_id_sha256_12", "reason_redacted", "hours", "limit",
    "error_codes", "excluded_error_codes", "error_code", "query_redacted",
}
FORBIDDEN_KEYS = {
    "prompt", "question", "raw_question", "raw_prompt", "messages", "content",
    "response", "raw_response", "llm_summary", "reason", "raw_arguments",
    "secret", "password", "api_key", "access_token", "run_id",
}


def _keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def _utc_valid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def inspect_trace(trace: dict) -> list[str]:
    """Return category codes only; never expose raw fields in an audit report."""
    findings = []
    if not re.fullmatch(r"[0-9a-f]{32}", str(trace.get("trace_id", ""))):
        findings.append("BAD_TRACE_ID")
    if not _utc_valid(trace.get("timestamp_utc")):
        findings.append("BAD_TIMESTAMP")
    if any(k in FORBIDDEN_KEYS for k in _keys(trace)):
        findings.append("FORBIDDEN_RAW_FIELD")
    if trace.get("response_text_recorded") is True:
        findings.append("UNSAFE_RESPONSE_CAPTURE")
    calls = trace.get("tool_call_count")
    tools = trace.get("tools_used")
    if not isinstance(calls, int) or calls < 0 or calls > 4:
        findings.append("INVALID_TOOL_COUNT")
    if not isinstance(tools, list) or len(tools) != calls:
        findings.append("TOOL_LIST_MISMATCH")
    if not isinstance(trace.get("latency_ms"), (int, float)):
        findings.append("MISSING_LATENCY")
    events = trace.get("events")
    if events is None:
        return sorted(set(findings))  # Backward-compatible legacy traces.
    if not isinstance(events, list):
        findings.append("INVALID_EVENT_TIMELINE")
        return sorted(set(findings))
    if trace.get("event_count") != len(events):
        findings.append("EVENT_COUNT_MISMATCH")
    types = [e.get("event_type") for e in events if isinstance(e, dict)]
    if any(t not in EVENT_TYPES for t in types) or len(types) != len(events):
        findings.append("UNEXPECTED_EVENT_TYPE")
    if "AGENT_STARTED" not in types:
        findings.append("MISSING_START_EVENT")
    if not any(t in types for t in ("AGENT_COMPLETED", "AGENT_FAILED")):
        findings.append("MISSING_TERMINAL_EVENT")
    if trace.get("status") == "rejected":
        if calls != 0 or "REQUEST_REJECTED" not in types:
            findings.append("REFUSAL_NOT_TRACED")
        if trace.get("escalation_decision") != "REFUSED":
            findings.append("REFUSAL_DECISION_MISSING")
    if trace.get("escalation_decision") == "PROPOSAL_ONLY":
        if "ESCALATION_PROPOSED" not in types:
            findings.append("PROPOSAL_NOT_TRACED")
        if not any(isinstance(t, dict) and t.get("tool") == "prepare_adf_escalation"
                   for t in tools or []):
            findings.append("PROPOSAL_TOOL_MISSING")
    # Every tool request should have an observed completion on a completed trace.
    requested = [e for e in events if isinstance(e, dict)
                 and e.get("event_type") == "TOOL_REQUESTED"]
    completed = [e for e in events if isinstance(e, dict)
                 and e.get("event_type") == "TOOL_COMPLETED"]
    if trace.get("status") == "completed" and (
        len(requested) != calls or len(completed) != calls
    ):
        findings.append("TOOL_TIMELINE_MISMATCH")
    enterprise = trace.get("execution_mode") in {"enterprise_llm", "deterministic_retrieval"}
    for event in events:
        if not isinstance(event, dict):
            continue
        if not _utc_valid(event.get("timestamp_utc")):
            findings.append("BAD_EVENT_TIMESTAMP")
        safe = event.get("arguments_safe")
        if safe is not None and (
            not isinstance(safe, dict) or set(safe) - ALLOWED_SAFE_ARGUMENTS
        ):
            findings.append("UNSAFE_ARGUMENT_KEYS")
        if enterprise and event.get("event_type") == "TOOL_REQUESTED" and (
            event.get("selection_source") is None
        ):
            findings.append("TOOL_SELECTION_UNDOCUMENTED")
        if enterprise and event.get("event_type") == "TOOL_COMPLETED" and (
            not isinstance(event.get("duration_ms"), (int, float))
        ):
            findings.append("TOOL_DURATION_MISSING")
        if event.get("event_type") == "REQUEST_REJECTED" and not event.get("reason_code"):
            findings.append("REFUSAL_REASON_MISSING")
    return sorted(set(findings))


def audit(path: Path, *, max_bytes: int = 30_000_000) -> dict:
    """Audit the local trace file; return only aggregate, nonidentifying metrics."""
    report = {
        "audit_name": "PROJECT3_OPERATIONAL_TRACES",
        "source_exists": path.is_file(),
        "records_checked": 0,
        "modern_timeline_count": 0,
        "legacy_without_timeline_count": 0,
        "rejected_count": 0,
        "proposal_only_count": 0,
        "tool_requests_count": 0,
        "tool_completions_count": 0,
        "issues": {},
        "audit_pass": False,
    }
    if not path.is_file():
        report["issues"] = {"TRACE_FILE_MISSING": 1}
        return report
    if path.stat().st_size > max_bytes:
        report["issues"] = {"TRACE_FILE_TOO_LARGE": 1}
        return report
    issues = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            trace = json.loads(line)
        except ValueError:
            issues["INVALID_JSONL"] += 1
            continue
        if not isinstance(trace, dict):
            issues["INVALID_RECORD"] += 1
            continue
        report["records_checked"] += 1
        if trace.get("events") is None:
            report["legacy_without_timeline_count"] += 1
        else:
            report["modern_timeline_count"] += 1
            events = trace.get("events")
            if isinstance(events, list):
                report["tool_requests_count"] += sum(
                    isinstance(e, dict) and e.get("event_type") == "TOOL_REQUESTED"
                    for e in events
                )
                report["tool_completions_count"] += sum(
                    isinstance(e, dict) and e.get("event_type") == "TOOL_COMPLETED"
                    for e in events
                )
        report["rejected_count"] += trace.get("status") == "rejected"
        report["proposal_only_count"] += trace.get("escalation_decision") == "PROPOSAL_ONLY"
        for issue in inspect_trace(trace):
            issues[issue] += 1
    report["issues"] = dict(sorted(issues.items()))
    report["audit_pass"] = report["records_checked"] > 0 and not issues
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Return nonzero if the available trace file fails audit")
    args = parser.parse_args()
    report = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OpsGuard AI — Audit des traces Projet 3")
    for field in ("records_checked", "modern_timeline_count", "legacy_without_timeline_count",
                  "rejected_count", "proposal_only_count", "tool_requests_count",
                  "tool_completions_count", "issues", "audit_pass"):
        print(f"  {field}: {report[field]}")
    print(f"Rapport de synthèse (sans texte utilisateur) : {args.output}")
    return int(args.check and not report["audit_pass"])


if __name__ == "__main__":
    raise SystemExit(main())
