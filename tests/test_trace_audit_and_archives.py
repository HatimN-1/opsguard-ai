"""Offline regression checks for the Project 3 audit and safe archive maintenance."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.archive_old_zip_files import archive_files, select_archives
from scripts.audit_project3_traces import audit, inspect_trace


def _event(event_type, **kwargs):
    return {"event_type": event_type, "timestamp_utc": datetime.now(UTC).isoformat(), **kwargs}


def _trace(*, status="completed", decision="NONE", tools=None, events=None):
    tools = tools or []
    events = events if events is not None else [_event("AGENT_STARTED"), _event("AGENT_COMPLETED")]
    return {
        "trace_id": uuid4().hex,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "final_response_status": status,
        "latency_ms": 17.2,
        "tool_call_count": len(tools),
        "iteration_count": len(tools),
        "tools_used": tools,
        "escalation_decision": decision,
        "response_text_recorded": False,
        "events": events,
        "event_count": len(events),
    }


def test_trace_audit_accepts_rejection_with_reason(tmp_path):
    t = _trace(status="rejected", decision="REFUSED", events=[
        _event("AGENT_STARTED"),
        _event("REQUEST_REJECTED", reason_code="UNAUTHORIZED_ACTION"),
        _event("AGENT_FAILED"),
    ])
    path = tmp_path / "agent_traces.jsonl"
    path.write_text(json.dumps(t) + "\n", encoding="utf-8")
    result = audit(path)
    assert result["audit_pass"] is True
    assert result["rejected_count"] == 1
    assert not result["issues"]


def test_trace_audit_validates_proposal_only(tmp_path):
    tools = [{"tool": name, "ok": True, "error": None,
              "selection_source": "evidence_plan"} for name in (
                  "query_adf_logs", "search_official_docs", "prepare_adf_escalation"
              )]
    events = [_event("AGENT_STARTED")]
    for n, tool in enumerate(tools, 1):
        events.append(_event("TOOL_REQUESTED", tool=tool["tool"], step=n,
                             selection_source="evidence_plan", arguments_safe={
                                 "run_id_sha256_12": "a" * 12,
                             }))
        events.append(_event("TOOL_COMPLETED", tool=tool["tool"], step=n,
                             ok=True, duration_ms=1.0))
    events += [_event("ESCALATION_PROPOSED", reason_code="PROPOSAL_PREPARED"),
               _event("AGENT_COMPLETED")]
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps(_trace(tools=tools, events=events,
                                       decision="PROPOSAL_ONLY")) + "\n", encoding="utf-8")
    report = audit(path)
    assert report["audit_pass"] is True
    assert report["proposal_only_count"] == 1
    assert report["tool_requests_count"] == report["tool_completions_count"] == 3


def test_trace_audit_rejects_raw_prompt_and_missing_refusal():
    t = _trace(status="rejected", decision="REFUSED")
    t["question"] = "private"
    findings = inspect_trace(t)
    assert "FORBIDDEN_RAW_FIELD" in findings
    assert "REFUSAL_NOT_TRACED" in findings


def test_trace_audit_handles_missing_file(tmp_path):
    report = audit(tmp_path / "missing.jsonl")
    assert report["audit_pass"] is False
    assert report["issues"] == {"TRACE_FILE_MISSING": 1}


def test_archive_dry_run_leaves_every_file_untouched(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "install.zip").write_bytes(b"fake zip")
    (root / "sauvegarde.zip").write_bytes(b"backup")
    (root / "main.py").write_text("print('keep')", encoding="utf-8")
    actions = archive_files(root, tmp_path / "archives", apply=False)
    assert len(actions) == 2
    assert all(status == "WOULD_MOVE" for _, status in actions)
    assert (root / "install.zip").is_file()
    assert (root / "main.py").is_file()
    assert not (tmp_path / "archives").exists()


def test_archive_moves_only_root_zip_without_overwrite(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "install.zip").write_bytes(b"fake zip")
    (root / "main.py").write_text("keep", encoding="utf-8")
    nested = root / "other"
    nested.mkdir()
    (nested / "nested.zip").write_bytes(b"keep")
    archive = tmp_path / "archives"
    assert [p.name for p in select_archives(root)] == ["install.zip"]
    actions = archive_files(root, archive, apply=True)
    assert actions == [("install.zip", "MOVED")]
    assert (archive / "install.zip").exists()
    assert (nested / "nested.zip").exists()
    assert (root / "main.py").exists()
    (root / "install.zip").write_bytes(b"new")
    actions2 = archive_files(root, archive, apply=True)
    assert actions2 == [("install.zip", "SKIPPED_EXISTS")]
    assert (root / "install.zip").read_bytes() == b"new"


def test_light_theme_css_is_plain_stylesheet():
    root = Path(__file__).resolve().parents[1]
    css = (root / "app/dashboard/assets/enterprise.css").read_text(encoding="utf-8")
    theme = (root / ".streamlit/config.toml").read_text(encoding="utf-8")
    app = (root / "app/dashboard/enterprise_app.py").read_text(encoding="utf-8")
    assert css.lstrip().startswith("/*") and "<style>" not in css
    assert 'base = "light"' in theme
    assert "st.html(CSS_FILE)" in app
    assert "SOURCE SIMULÉE · LOCALE" not in app
    assert "Données synthétiques" not in app  # Disclosure uses accurate full sentence in governance.
