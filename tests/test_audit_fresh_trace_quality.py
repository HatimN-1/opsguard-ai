"""Offline tests of the read-only trace quality audit."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from scripts.audit_fresh_trace_quality_readonly import audit_file, audit_record


def sample_record():
    start = datetime(2026, 11, 12, tzinfo=UTC)

    def stamp(seconds):
        return (start + timedelta(seconds=seconds)).isoformat()

    return {
        "trace_id": "test-only-trace", "timestamp_utc": stamp(4),
        "latency_ms": 4000, "tool_call_count": 1, "event_count": 4,
        "events": [
            {"event_type": "AGENT_STARTED", "timestamp_utc": stamp(0)},
            {"event_type": "TOOL_REQUESTED", "timestamp_utc": stamp(1),
             "tool": "query_adf_logs", "selection_source": "evidence_plan", "step": 1},
            {"event_type": "TOOL_COMPLETED", "timestamp_utc": stamp(2),
             "tool": "query_adf_logs", "duration_ms": 1000, "ok": True, "step": 1},
            {"event_type": "AGENT_COMPLETED", "timestamp_utc": stamp(3)},
        ],
    }


def test_complete_trace_passes():
    errors, warnings, metrics = audit_record(sample_record())
    assert not errors
    assert not warnings
    assert metrics["tool_requested"] == 1


def test_missing_selection_fails():
    trace = sample_record()
    del trace["events"][1]["selection_source"]
    errors, _, _ = audit_record(trace)
    assert errors["TOOL_SELECTION_UNDOCUMENTED"] == 1


def test_missing_duration_fails():
    trace = sample_record()
    del trace["events"][2]["duration_ms"]
    errors, _, _ = audit_record(trace)
    assert errors["TOOL_DURATION_MISSING_OR_INVALID"] == 1


def test_unpaired_tool_fails():
    trace = sample_record()
    trace["events"].pop(2)
    trace["event_count"] = 3
    errors, _, _ = audit_record(trace)
    assert errors["TOOL_REQUEST_WITHOUT_COMPLETION"] == 1


def test_sensitive_content_is_counted_not_reported():
    trace = sample_record()
    trace["events"][1]["password"] = "do-not-echo"
    errors, _, _ = audit_record(trace)
    assert errors["SENSITIVE_FIELD_NAME"] == 1
    assert "do-not-echo" not in str(errors)


def test_marker_scopes_audit_to_only_new_rows(tmp_path):
    source = tmp_path / "agent_traces.jsonl"
    old = json.dumps({"legacy": True}) + "\n"
    source.write_text(old + json.dumps(sample_record()) + "\n", encoding="utf-8")
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"lines": 1, "size_bytes": len(old.encode())}), encoding="utf-8")
    code, report = audit_file(source, marker)
    assert code == 0
    assert report["records_checked"] == 1
    assert report["result"] == "PASS"
    assert "test-only-trace" not in json.dumps(report)


def test_tool_completion_needs_status():
    trace = sample_record()
    del trace["events"][2]["ok"]
    errors, _, _ = audit_record(trace)
    assert errors["TOOL_RESULT_STATUS_MISSING"] == 1


def test_out_of_order_events_fail():
    trace = sample_record()
    trace["events"][2]["timestamp_utc"] = "2026-11-11T23:59:00+00:00"
    errors, _, _ = audit_record(trace)
    assert errors["EVENTS_OUT_OF_ORDER"] >= 1


def test_duplicate_trace_id_fails(tmp_path):
    source = tmp_path / "agent_traces.jsonl"
    record = json.dumps(sample_record()) + "\n"
    source.write_text(record + record, encoding="utf-8")
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"lines": 0, "size_bytes": 0}), encoding="utf-8")
    code, report = audit_file(source, marker)
    assert code == 1
    assert report["errors"]["DUPLICATE_TRACE_ID"] == 1
