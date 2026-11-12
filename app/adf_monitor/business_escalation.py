"""Simulated human approval workflow for ADF evidence, not real authentication.

An LLM cannot call the write methods. Streamlit uses them only after explicit
button interactions and a distinct simulated operator/approver decision.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.adf_monitor.business_catalog import require_business_pipeline
from app.adf_monitor.company_monitor import list_business_runs
from app.adf_monitor.source import ROOT, external_workspace

ROLES = {"alice": "operator", "charlie": "operator", "bob": "approver", "eve": "viewer"}


class EscalationError(ValueError):
    pass


def _path(root: Path | None = None) -> Path:
    folder = (root or external_workspace()).resolve()
    if folder == ROOT or ROOT in folder.parents:
        raise EscalationError("The incident log cannot be inside the repository")
    path = folder / "adf_case_events.jsonl"
    if path.is_symlink() or path.exists() and path.stat().st_size > 2_000_000:
        raise EscalationError("Unsafe or oversized incident file")
    return path


def _validate_subject(pipeline_id: str, run_id: str, reason: str, root: Path | None) -> None:
    require_business_pipeline(pipeline_id)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", run_id):
        raise EscalationError("Run ID invalid")
    if not isinstance(reason, str) or not 15 <= len(reason.strip()) <= 300:
        raise EscalationError("Motif attendu : entre 15 et 300 caractères")
    runs = list_business_runs(hours=720, root=root)
    if not any(x["pipeline_name"] == pipeline_id and x["run_id"] == run_id for x in runs):
        raise EscalationError("Exécution absente des journaux autorisés")


def prepare_case(pipeline_id: str, run_id: str, reason: str, *, root: Path | None = None) -> dict:
    """Pure/read-only proposal: must not create a ticket."""
    _validate_subject(pipeline_id, run_id, reason, root)
    return {
        "pipeline_id": pipeline_id, "run_id": run_id,
        "reason": reason.strip(), "status": "PROPOSAL_ONLY",
        "human_approval_required": True, "ticket_created": False,
    }


def list_cases(*, root: Path | None = None) -> list[dict]:
    path = _path(root)
    if not path.exists():
        return []
    states: dict[str, dict] = {}
    with path.open(encoding="utf-8") as file:
        for n, line in enumerate(file):
            if n >= 10000:
                raise EscalationError("Incident event limit exceeded")
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            cid = event.get("case_id")
            if not isinstance(cid, str) or not re.fullmatch(r"ADFCASE-[0-9a-f]{12}", cid):
                continue
            if event.get("type") == "REQUEST" and cid not in states:
                states[cid] = {**event, "status": "PENDING_APPROVAL"}
            elif event.get("type") == "APPROVAL" and cid in states:
                states[cid]["status"] = "APPROVED"
                states[cid]["approved_by"] = event.get("actor")
    return list(reversed(list(states.values())))


def _append(event: dict, *, root: Path | None = None) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def request_case(proposal: dict, *, actor: str, root: Path | None = None) -> dict:
    if ROLES.get(actor) != "operator":
        raise EscalationError("Seul un opérateur simulé peut soumettre un dossier")
    if proposal.get("status") != "PROPOSAL_ONLY":
        raise EscalationError("A proposal must be prepared first")
    _validate_subject(proposal.get("pipeline_id"), proposal.get("run_id"),
                      proposal.get("reason"), root)
    if any(x["pipeline_id"] == proposal["pipeline_id"] and
           x["run_id"] == proposal["run_id"] for x in list_cases(root=root)):
        raise EscalationError("Un dossier existe déjà pour cette exécution")
    event = {
        "type": "REQUEST", "case_id": "ADFCASE-" + uuid4().hex[:12],
        "pipeline_id": proposal["pipeline_id"], "run_id": proposal["run_id"],
        "reason": proposal["reason"], "actor": actor,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
    _append(event, root=root)
    return {**event, "status": "PENDING_APPROVAL"}


def approve_case(case_id: str, *, actor: str, root: Path | None = None) -> dict:
    if ROLES.get(actor) != "approver":
        raise EscalationError("Seul un approbateur simulé peut valider un dossier")
    cases = list_cases(root=root)
    item = next((c for c in cases if c["case_id"] == case_id), None)
    if not item or item["status"] != "PENDING_APPROVAL":
        raise EscalationError("Dossier absent ou déjà approuvé")
    _append({"type": "APPROVAL", "case_id": case_id, "actor": actor,
             "timestamp_utc": datetime.now(UTC).isoformat()}, root=root)
    return {"case_id": case_id, "status": "APPROVED", "approved_by": actor}
