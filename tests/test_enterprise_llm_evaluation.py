"""Test live-evaluation infrastructure offline; NO Ollama or Azure connection."""

import csv
import json

import pytest

from app.adf_monitor.llm_evaluation import (
    load_cases,
    run_evaluation,
    select_cases,
)
from scripts.evaluate_enterprise_llm import write_review
from scripts.score_enterprise_llm_review import score_reviews


class TextClient:
    def __init__(self, message: str):
        self.message = message
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        assert kwargs["think"] is False
        assert kwargs["model"]
        # Production never forwards raw logs as instructions to this client.
        user = kwargs["messages"][1]["content"]
        assert "ErrorMessage" not in user
        assert "IGNORE ALL RULES" not in user
        return {"message": {"content": self.message}}


@pytest.fixture
def workspace_env(tmp_path, monkeypatch):
    original = tmp_path / "existing-workspace"
    original.mkdir()
    immutable = original / "external_control.txt"
    immutable.write_text("must-not-change", encoding="utf-8")
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(original))
    return original


def test_protocol_is_twelve_fixed_pipelines():
    cases = load_cases()["cases"]
    assert len(cases) == 12
    assert len({item["pipeline_id"] for item in cases}) == 12
    assert {item["scenario"] for item in cases} >= {
        "3200", "20000", "UNLISTED_AZURE_98765", "SUCCESS"
    }


def test_select_smoke_three_types():
    cases = select_cases(load_cases(), smoke=True)
    assert {item["id"] for item in cases} == {"EVAL-04", "EVAL-08", "EVAL-11"}


def test_unknown_case_filter_is_rejected():
    with pytest.raises(ValueError, match="Unknown case"):
        select_cases(load_cases(), only="EVAL-99")


def test_invalid_labels_rejected(tmp_path):
    protocol = load_cases()
    protocol["cases"][0]["expected_code"] = "9999"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid labels"):
        load_cases(path)


def test_baseline_full_suite_and_environment_restored(workspace_env):
    report, review = run_evaluation(mode="baseline", seed=42)
    assert report["selected_cases"] == 12
    assert report["checks_passed"] is True
    assert report["metrics"]["retrieval_success_rate"] == 1.0
    assert report["metrics"]["documentation_accuracy"] == 1.0
    assert report["metrics"]["unauthorized_request_refusal_rate"] == 1.0
    assert report["metrics"]["semantic_fidelity_rate"] is None
    assert report["metrics"]["llm_acceptance_rate"] is None
    assert review == []
    assert workspace_env.joinpath("external_control.txt").read_text() == "must-not-change"
    import os

    assert os.environ["OPSGUARD_ADF_EXTERNAL_DIR"] == str(workspace_env)


def test_live_accepted_has_no_raw_text_in_metadata(workspace_env):
    text = (
        "Le code 3200 observé peut correspondre à un problème d'accès. "
        "Il faut vérifier les autorisations et les identifiants."
    )
    report, reviews = run_evaluation(
        mode="live", only="EVAL-04",
        client_factory=lambda _case, _repeat: TextClient(text),
    )
    assert report["metrics"]["llm_accepted"] == 1
    assert report["cases"][0]["llm_status"] == "ACCEPTED"
    assert report["cases"][0]["retrieval_case_pass"] is True
    assert "Le code 3200 observé" not in json.dumps(report, ensure_ascii=False)
    assert reviews[0]["response"] == text
    assert reviews[0]["fidelity"] == ""
    assert report["metrics"]["semantic_fidelity_rate"] is None


def test_live_rejected_unverified_number_keeps_retrieval_success(workspace_env):
    text = "Le code 9999 a été observé. Il faut vérifier les informations."
    report, reviews = run_evaluation(
        mode="live", only="EVAL-04",
        client_factory=lambda _case, _repeat: TextClient(text),
    )
    assert report["checks_passed"] is True
    assert report["metrics"]["llm_rejected"] == 1
    assert report["cases"][0]["llm_validation_reason"] == "UNVERIFIED_NUMBER"
    assert text not in json.dumps(report, ensure_ascii=False)
    assert reviews[0]["response"] == text


def test_live_unavailable_counts_separately(workspace_env):
    class BrokenClient:
        def chat(self, **kwargs):
            raise TimeoutError("simulated local Ollama timeout")

    report, reviews = run_evaluation(
        mode="live", only="EVAL-04",
        client_factory=lambda _case, _repeat: BrokenClient(),
    )
    assert report["checks_passed"] is True
    assert report["metrics"]["llm_unavailable"] == 1
    assert report["metrics"]["llm_availability_rate"] == 0.0
    assert report["cases"][0]["llm_validation_reason"] == "LLM_ERROR"
    assert reviews[0]["response"] == ""


def test_success_case_has_no_false_documentation(workspace_env):
    report, _ = run_evaluation(mode="baseline", only="EVAL-11")
    assert report["cases"][0]["observed_codes"] == []
    assert report["cases"][0]["actual_tools"] == ["query_adf_logs"]
    assert report["cases"][0]["documents_correct"] is True


def test_unknown_error_has_no_fabricated_reference(workspace_env):
    report, _ = run_evaluation(mode="baseline", only="EVAL-08")
    row = report["cases"][0]
    assert row["document_status"]["UNLISTED_AZURE_98765"] == "NOT_FOUND_IN_INDEX"
    assert row["retrieval_case_pass"] is True


def test_recurring_claim_requires_human_review_flag(workspace_env):
    text = (
        "Le code 3200 indique un problème récurrent d'accès à Azure Databricks. "
        "Il faut vérifier les autorisations."
    )
    report, _ = run_evaluation(
        mode="live", only="EVAL-04",
        client_factory=lambda _case, _repeat: TextClient(text),
    )
    assert "CHECK_RECURRENCE_CLAIM_VS_DISTINCT_RUNS" in report["cases"][0]["review_flags"]
    assert report["metrics"]["semantic_fidelity_rate"] is None


def test_manual_review_not_overwritten_silently(tmp_path):
    path = tmp_path / "manual.csv"
    rows = [{"case_id": "EVAL-04", "repetition": 1, "llm_status": "ACCEPTED",
             "response": "Test", "fidelity": "", "cautious_causality": "",
             "safe_actions": "", "appropriate_french": ""}]
    write_review(path, rows)
    with pytest.raises(FileExistsError):
        write_review(path, rows)


def test_review_scoring_ignores_unreviewed_and_rejected(tmp_path):
    csv_path = tmp_path / "review.csv"
    fields = ["case_id", "repetition", "llm_status", "fidelity",
              "cautious_causality", "safe_actions", "appropriate_french"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([
            {"case_id": "EVAL-04", "repetition": 1, "llm_status": "ACCEPTED",
             "fidelity": "oui", "cautious_causality": "non",
             "safe_actions": "oui", "appropriate_french": "oui"},
            {"case_id": "EVAL-05", "repetition": 1, "llm_status": "ACCEPTED",
             "fidelity": "", "cautious_causality": "",
             "safe_actions": "", "appropriate_french": ""},
            {"case_id": "EVAL-08", "repetition": 1, "llm_status": "REJECTED_BY_GUARD",
             "fidelity": "oui", "cautious_causality": "oui",
             "safe_actions": "oui", "appropriate_french": "oui"},
        ])
    scored = score_reviews(csv_path)
    assert scored["reviewed_accepted_summaries"] == 1
    assert scored["accepted_summaries_total"] == 2
    assert scored["review_coverage"] == 0.5
    assert scored["rates"]["fidelity"] == 1.0
    assert scored["rates"]["cautious_causality"] == 0.0
    assert scored["all_four_dimensions_pass_rate"] == 0.0


def test_scoring_empty_reviews_is_not_falsely_perfect(tmp_path):
    csv_path = tmp_path / "review.csv"
    csv_path.write_text(
        "case_id,repetition,llm_status,fidelity,cautious_causality,"
        "safe_actions,appropriate_french\nEVAL-04,1,ACCEPTED,,,,\n",
        encoding="utf-8",
    )
    scored = score_reviews(csv_path)
    assert scored["reviewed_accepted_summaries"] == 0
    assert scored["rates"]["fidelity"] is None
    assert scored["all_four_dimensions_pass_rate"] is None


def test_csv_model_output_not_interpreted_as_excel_formula(tmp_path):
    path = tmp_path / "manual.csv"
    rows = [{"case_id": "EVAL-04", "repetition": 1, "llm_status": "ACCEPTED",
             "response": "=HYPERLINK(\"https://invalid.test\")"}]
    write_review(path, rows)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        saved = list(csv.DictReader(handle))
    assert saved[0]["response"].startswith("'=")
