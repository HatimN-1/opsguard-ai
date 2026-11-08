
"""Simulated ticket workflow with role checks and human approval."""

import json
from itertools import count
from pathlib import Path
from threading import Lock

INCIDENTS_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "incidents.json"
)

DEMO_ROLES = {
    "alice": "operator",
    "charlie": "operator",
    "bob": "approver",
    "eve": "viewer",
}

_tickets: dict[str, dict] = {}
_counter = count(1)
_lock = Lock()


def request_ticket_creation(
    incident_id: str, reason: str, user: str
) -> dict:
    """Create a pending request without external side effects."""

    if DEMO_ROLES.get(user) != "operator":
        raise PermissionError(
            "Only operators can request tickets"
        )

    with INCIDENTS_FILE.open(encoding="utf-8") as file:
        valid_ids = {
            item["incident_id"]
            for item in json.load(file)
        }

    if incident_id not in valid_ids:
        raise LookupError("Incident not found")

    with _lock:
        if any(
            ticket["incident_id"] == incident_id
            and ticket["status"] in {
                "PENDING_APPROVAL",
                "APPROVED",
            }
            for ticket in _tickets.values()
        ):
            raise ValueError(
                "A ticket already exists for this incident"
            )

        ticket_id = f"TCK-{next(_counter):04d}"

        ticket = {
            "ticket_id": ticket_id,
            "incident_id": incident_id,
            "reason": reason,
            "requested_by": user,
            "status": "PENDING_APPROVAL",
            "approved_by": None,
        }

        _tickets[ticket_id] = ticket

        return ticket.copy()


def approve_ticket(ticket_id: str, user: str) -> dict:
    """Approve a pending ticket using the demo approver role."""

    if DEMO_ROLES.get(user) != "approver":
        raise PermissionError(
            "Only approvers can approve tickets"
        )

    with _lock:
        ticket = _tickets.get(ticket_id)

        if ticket is None:
            raise LookupError("Ticket not found")

        if ticket["status"] != "PENDING_APPROVAL":
            raise ValueError(
                "Ticket is not pending approval"
            )

        ticket["status"] = "APPROVED"
        ticket["approved_by"] = user

        return ticket.copy()


def reset_tickets_for_tests() -> None:
    """Reset the temporary store before each test."""

    global _counter

    with _lock:
        _tickets.clear()
        _counter = count(1)
