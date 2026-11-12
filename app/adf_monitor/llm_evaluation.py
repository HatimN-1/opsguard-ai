"""Reproducible, evidence-labelled evaluation of the Northstar ADF agent.

Real Ollama inference is *only* used in mode='live'; baseline and CI are offline.
Synthetic fixtures are created in a temporary directory outside the project.
The report contains metadata only; raw LLM answers require explicit export.
"""

import hashlib
import json
import math
import os
import re
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.adf_monitor.business_catalog import catalog_fingerprint, known_business_ids
from app.adf_monitor.company_runtime import append_business_run
from app.adf_monitor.enterprise_agent import (
    LLM_CONTEXT_VERSION,
    InvestigationPlanError,
    investigate_company,
    plan_investigation,
)
from app.adf_monitor.llm_guard import LLM_GUARD_VERSION

ROOT = Path(__file__).resolve().parents[2]
CASES_FILE = ROOT / "evaluation" / "enterprise_llm_cases.json"
DOCUMENTS_FILE = ROOT / "docs" / "microsoft_adf_index.json"
SMOKE_IDS = frozenset({"EVAL-04", "EVAL-08", "EVAL-11"})
_WARNING_RECURRENCE = re.compile(
    r"\b(?:persistant\w*|r[eé]current\w*|r[eé]p[eé]t[eé]\w*|syst[eé]matique\w*)\b",
    re.IGNORECASE,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path = CASES_FILE) -> dict:
    """Validate a versioned, independent label set before using it."""
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict) or not isinstance(protocol.get("cases"), list):
        raise TypeError("Invalid evaluation protocol")
    items = protocol["cases"]
    if not items or len(items) > 50:
        raise ValueError("Invalid number of evaluation cases")
    ids = set()
    company_ids = set(known_business_ids())
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Evaluation case must be an object")
        case_id = item.get("id")
        pipeline = item.get("pipeline_id")
        scenario = item.get("scenario")
        expected = item.get("expected_code")
        doc_status = item.get("expected_document_status")
        question = item.get("question")
        if (
            not isinstance(case_id, str)
            or not re.fullmatch(r"EVAL-\d{2}", case_id)
            or case_id in ids
            or pipeline not in company_ids
            or not isinstance(scenario, str)
            or not re.fullmatch(r"[A-Z0-9_]{2,50}", scenario)
            or expected != (None if scenario == "SUCCESS" else scenario)
            or doc_status not in {"DOCUMENTED", "NOT_FOUND_IN_INDEX", "NO_ERROR"}
            or (scenario == "SUCCESS") != (doc_status == "NO_ERROR")
            or not isinstance(question, str)
            or not 10 <= len(question) <= 500
            or pipeline not in question
        ):
            raise ValueError(f"Invalid labels in evaluation case {case_id!r}")
        ids.add(case_id)
    requests = protocol.get("forbidden_requests")
    if not isinstance(requests, list) or not requests or not all(
        isinstance(query, str) and query.strip() for query in requests
    ):
        raise ValueError("Missing forbidden request cases")
    return protocol


def select_cases(
    protocol: dict, *, smoke: bool = False, only: str | None = None,
    max_cases: int | None = None,
) -> list[dict]:
    """Choose a stable subset; don't silently replace the fixed business catalog."""
    cases = list(protocol["cases"])
    if smoke:
        cases = [item for item in cases if item["id"] in SMOKE_IDS]
        if len(cases) != len(SMOKE_IDS):
            raise ValueError("Smoke scenarios are missing")
    if only is not None:
        cases = [item for item in cases if item["id"] == only]
        if not cases:
            raise ValueError("Unknown case identifier")
    if max_cases is not None:
        if max_cases < 1:
            raise ValueError("max_cases must be positive")
        cases = cases[:max_cases]
    if not cases:
        raise ValueError("No cases selected")
    return cases


class CaptureClient:
    """Capture the model response in memory for *optional* manual review export."""

    def __init__(self, client: Any):
        self.client = client
        self.raw = ""
        self.calls = 0

    def chat(self, **kwargs: Any) -> Any:
        self.calls += 1
        response = self.client.chat(**kwargs)
        message = (
            response.get("message") if isinstance(response, dict)
            else getattr(response, "message", None)
        )
        content = (
            message.get("content", "") if isinstance(message, dict)
            else getattr(message, "content", "")
        )
        self.raw = str(content or "")[:5000]
        return response


class UnavailableClient:
    """Let the agent report UNAVAILABLE rather than abort the whole evaluation."""

    def chat(self, **kwargs: Any) -> Any:
        raise RuntimeError("Local LLM client unavailable")


def _make_client() -> Any:
    try:
        from ollama import Client

        return Client(
            host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"), timeout=65.0
        )
    except (ImportError, ValueError, OSError):
        return UnavailableClient()


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    return round(sorted_values[math.ceil(0.95 * len(values)) - 1], 2)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _case_outcomes(result: dict, case: dict) -> dict:
    facts = result.get("facts") or {}
    errors = facts.get("errors") or []
    observed = sorted({str(item.get("error_code")) for item in errors
                       if isinstance(item, dict) and item.get("error_code")})
    expected = [case["expected_code"]] if case["expected_code"] else []
    codes_correct = observed == expected
    status = result.get("document_status") or {}
    if case["expected_document_status"] == "NO_ERROR":
        documents_correct = not status and not result.get("documents")
    else:
        documents_correct = status.get(case["expected_code"]) == case[
            "expected_document_status"
        ]
    expected_tools = ["query_adf_logs"] + (
        ["search_official_docs"] if case["expected_code"] else []
    )
    actual_tools = [x.get("tool") for x in result.get("tools_used", [])]
    tool_ok = all(x.get("ok") is True or x.get("error") == "NOT_FOUND"
                  for x in result.get("tools_used", []))
    tools_correct = (
        actual_tools == expected_tools and result.get("tool_call_count") <= 4
        and tool_ok
    )
    isolated = (
        result.get("plan", {}).get("pipeline_id") == case["pipeline_id"]
        and result.get("plan", {}).get("run_id") == result.get("_expected_run_id")
    )
    return {
        "codes_correct": codes_correct,
        "documents_correct": documents_correct,
        "tools_correct": tools_correct,
        "run_isolation_correct": isolated,
        "observed_codes": observed,
        "document_status": status,
        "actual_tools": actual_tools,
        "tool_errors": [x.get("error") for x in result.get("tools_used", [])],
        "retrieval_case_pass": bool(
            result.get("status") == "completed" and codes_correct
            and documents_correct and tools_correct and isolated
        ),
    }


def _summary_flags(text: str, case: dict) -> list[str]:
    """A review hint, NOT a semantic truth classifier."""
    flags = []
    if text and _WARNING_RECURRENCE.search(text):
        flags.append("CHECK_RECURRENCE_CLAIM_VS_DISTINCT_RUNS")
    if text and case["scenario"] == "SUCCESS" and re.search(
        r"\b(?:[eé]chec|panne|incident|erreur)\b", text, re.IGNORECASE
    ):
        flags.append("CHECK_FALSE_INCIDENT_CLAIM")
    if text and case["expected_document_status"] == "NOT_FOUND_IN_INDEX":
        flags.append("CHECK_UNDOCUMENTED_ERROR_CLAIMS")
    return flags


def run_evaluation(
    *, mode: str = "baseline", smoke: bool = False, only: str | None = None,
    max_cases: int | None = None, repetitions: int = 1, seed: int = 42,
    client_factory: Any = None, protocol_path: Path = CASES_FILE,
) -> tuple[dict, list[dict]]:
    """Run labelled scenarios without touching existing external company logs.

    The returned report omits prompts and model answers. Review rows hold
    answers only in memory; the CLI exports them only on explicit request.
    """
    if mode not in {"baseline", "live"}:
        raise ValueError("Mode must be baseline or live")
    if not 1 <= repetitions <= 5:
        raise ValueError("Repetitions must be between 1 and 5")
    protocol = load_cases(protocol_path)
    cases = select_cases(protocol, smoke=smoke, only=only, max_cases=max_cases)
    report_cases = []
    review_rows = []
    forbidden_results = []
    previous_source = os.environ.get("OPSGUARD_ADF_SOURCE")
    previous_dir = os.environ.get("OPSGUARD_ADF_EXTERNAL_DIR")
    try:
        with TemporaryDirectory(prefix="opsguard-qwen-evaluation-") as temp_dir:
            workspace = Path(temp_dir)
            os.environ["OPSGUARD_ADF_SOURCE"] = "external_demo"
            os.environ["OPSGUARD_ADF_EXTERNAL_DIR"] = str(workspace)
            trace_path = workspace / "agent_traces_eval.jsonl"
            for case_index, case in enumerate(cases):
                fixture = append_business_run(
                    case["pipeline_id"], scenario=case["scenario"],
                    activities=36, seed=seed + case_index,
                    root=workspace,
                )
                for repeat_index in range(1, repetitions + 1):
                    capture = None
                    if mode == "live":
                        try:
                            client = (
                                client_factory(case, repeat_index)
                                if client_factory is not None else _make_client()
                            )
                        except Exception:  # noqa: BLE001
                            client = UnavailableClient()
                        capture = CaptureClient(client)
                    response = investigate_company(
                        case["question"], pipeline_id=case["pipeline_id"],
                        run_id=fixture["run_id"], hours=24,
                        use_llm=mode == "live", client=capture,
                        trace_path=trace_path,
                    )
                    response["_expected_run_id"] = fixture["run_id"]
                    outcomes = _case_outcomes(response, case)
                    summary = (capture.raw if capture else "")
                    flags = _summary_flags(summary, case)
                    llm_status = response.get("llm_status", "NOT_REQUESTED")
                    record = {
                        "case_id": case["id"],
                        "pipeline_id": case["pipeline_id"],
                        "repetition": repeat_index,
                        "scenario": case["scenario"],
                        "run_id": fixture["run_id"],
                        "expected_error_code": case["expected_code"],
                        "expected_document_status": case["expected_document_status"],
                        "llm_status": llm_status,
                        "llm_call_count": capture.calls if capture else 0,
                        "llm_validation_reason": response.get("llm_validation_reason"),
                        "llm_response_characters": len(summary),
                        "llm_response_sha256": (
                            hashlib.sha256(summary.encode("utf-8")).hexdigest()
                            if summary else None
                        ),
                        "manual_review_required": mode == "live",
                        "review_flags": flags,
                        "latency_ms": response.get("latency_ms"),
                        "trace_id": response.get("trace_id"),
                        "tool_call_count": response.get("tool_call_count"),
                        **outcomes,
                    }
                    report_cases.append(record)
                    if mode == "live":
                        review_rows.append({
                            "case_id": case["id"],
                            "repetition": repeat_index,
                            "pipeline_id": case["pipeline_id"],
                            "expected_error_code": case["expected_code"] or "NONE",
                            "expected_document_status": case["expected_document_status"],
                            "llm_status": llm_status,
                            "response": summary,
                            "review_flags": ";".join(flags),
                            "fidelity": "",
                            "cautious_causality": "",
                            "safe_actions": "",
                            "appropriate_french": "",
                            "review_notes": "",
                        })
            for question in protocol["forbidden_requests"]:
                try:
                    plan_investigation(question)
                except InvestigationPlanError:
                    forbidden_results.append(True)
                else:
                    forbidden_results.append(False)
    finally:
        if previous_source is None:
            os.environ.pop("OPSGUARD_ADF_SOURCE", None)
        else:
            os.environ["OPSGUARD_ADF_SOURCE"] = previous_source
        if previous_dir is None:
            os.environ.pop("OPSGUARD_ADF_EXTERNAL_DIR", None)
        else:
            os.environ["OPSGUARD_ADF_EXTERNAL_DIR"] = previous_dir

    total = len(report_cases)
    accepted = sum(item["llm_status"] == "ACCEPTED" for item in report_cases)
    rejected = sum(item["llm_status"] == "REJECTED_BY_GUARD" for item in report_cases)
    unavailable = sum(item["llm_status"] == "UNAVAILABLE" for item in report_cases)
    elapsed = [float(item["latency_ms"]) for item in report_cases
               if isinstance(item.get("latency_ms"), (int, float))]
    retrieval_passed = sum(item["retrieval_case_pass"] for item in report_cases)
    safety_passed = sum(forbidden_results)
    tool_calls = sum(item["tool_call_count"] for item in report_cases)
    tool_not_found = 0
    tool_failures = 0
    unexpected_tool_failures = 0
    for item in report_cases:
        # Detailed outcomes are reported without exposing tool arguments or results.
        tool_not_found += sum(
            status == "NOT_FOUND" for status in item.get("tool_errors", [])
        )
        tool_failures += sum(
            status is not None for status in item.get("tool_errors", [])
        )
        unexpected_tool_failures += sum(
            status not in (None, "NOT_FOUND")
            for status in item.get("tool_errors", [])
        )
    validation_reasons = Counter(item["llm_validation_reason"] for item in report_cases
                                 if item["llm_validation_reason"] is not None)
    metrics = {
        "retrieval_success_rate": _ratio(retrieval_passed, total),
        "tool_selection_rate": _ratio(sum(x["tools_correct"] for x in report_cases), total),
        "observed_code_accuracy": _ratio(sum(x["codes_correct"] for x in report_cases), total),
        "documentation_accuracy": _ratio(sum(x["documents_correct"] for x in report_cases), total),
        "unauthorized_request_refusal_rate": _ratio(safety_passed, len(forbidden_results)),
        "tool_calls_mean": round(statistics.mean(x["tool_call_count"] for x in report_cases), 3),
        "tool_failed_or_notfound_rate": _ratio(tool_failures, tool_calls),
        "tool_notfound_rate": _ratio(tool_not_found, tool_calls),
        "unexpected_tool_failure_rate": _ratio(unexpected_tool_failures, tool_calls),
        "latency_mean_ms": round(statistics.mean(elapsed), 2) if elapsed else None,
        "latency_p95_ms": _p95(elapsed),
        "llm_accepted": accepted,
        "llm_rejected": rejected,
        "llm_unavailable": unavailable,
        "llm_calls_mean": round(statistics.mean(
            item["llm_call_count"] for item in report_cases
        ), 3) if mode == "live" else None,
        "llm_retried_cases": sum(
            item["llm_call_count"] > 1 for item in report_cases
        ),
        "llm_retried_accepted": sum(
            item["llm_call_count"] > 1 and item["llm_status"] == "ACCEPTED"
            for item in report_cases
        ),
        "llm_acceptance_rate": _ratio(accepted, total) if mode == "live" else None,
        "llm_availability_rate": _ratio(total - unavailable, total) if mode == "live" else None,
        "llm_validation_rejection_reasons": dict(sorted(validation_reasons.items())),
        "semantic_fidelity_rate": None,
        "semantic_fidelity_status": (
            "MANUAL_REVIEW_REQUIRED" if mode == "live" else "NOT_APPLICABLE"
        ),
    }
    report = {
        "protocol": protocol["protocol"],
        "evaluation_mode": "LIVE_LOCAL_OLLAMA" if mode == "live" else "OFFLINE_RETRIEVAL",
        "label_source": "VERSIONED_SYNTHETIC_SCENARIOS_NOT_LLM_OUTPUT",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "seed": seed,
        "repetitions": repetitions,
        "selected_cases": len(cases),
        "total_investigations": total,
        "catalog_pipelines": len(known_business_ids()),
        "catalog_fingerprint": catalog_fingerprint(),
        "llm_context_version": LLM_CONTEXT_VERSION,
        "llm_guard_version": LLM_GUARD_VERSION,
        "protocol_sha256": _sha256(protocol_path),
        "documentation_sha256": _sha256(DOCUMENTS_FILE),
        "model": os.getenv("OLLAMA_MODEL", "qwen3:1.7b") if mode == "live" else None,
        "checks": {
            "retrieval_cases_all_pass": retrieval_passed == total,
            "forbidden_requests_all_refused": safety_passed == len(forbidden_results),
            "at_most_four_tools": all(x["tool_call_count"] <= 4 for x in report_cases),
        },
        "checks_passed": retrieval_passed == total and all(forbidden_results)
        and all(x["tool_call_count"] <= 4 for x in report_cases),
        "metrics": metrics,
        "cases": report_cases,
        "limitations": [
            "Synthetic ADF-shaped logs, not production telemetry",
            "Fixtures preserve seeds and labels, but timestamps and run UUIDs vary",
            "Accepted LLM text is not semantically proven correct by token validation",
            "LLM evidence quality requires manual review; no automatic hallucination score",
            "This benchmark does not evaluate Ollama tool selection: tools follow evidence_plan",
            "The report stores metadata only; model text requires explicit review export",
        ],
    }
    return report, review_rows
