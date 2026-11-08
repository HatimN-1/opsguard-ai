
"""Incident Manager permission and workflow tests."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.tools.incident_tool import reset_tickets_for_tests

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store() -> None:
    reset_tickets_for_tests()


def submit(
    user: str = "alice",
    incident_id: str = "INC-001",
):
    return client.post(
        "/tickets",
        headers={"X-Demo-User": user},
        json={
            "incident_id": incident_id,
            "reason": "Investigate ETL schema mismatch",
        },
    )


def test_operator_requests_pending_ticket() -> None:
    response = submit()

    assert response.status_code == 201
    assert response.json()["status"] == "PENDING_APPROVAL"
    assert response.json()["approved_by"] is None


def test_approver_approves_ticket() -> None:
    ticket_id = submit().json()["ticket_id"]

    response = client.post(
        f"/tickets/{ticket_id}/approve",
        headers={"X-Demo-User": "bob"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["approved_by"] == "bob"


def test_viewer_cannot_create_ticket() -> None:
    response = submit("eve")
    assert response.status_code == 403


def test_operator_cannot_approve_ticket() -> None:
    ticket_id = submit().json()["ticket_id"]

    response = client.post(
        f"/tickets/{ticket_id}/approve",
        headers={"X-Demo-User": "charlie"},
    )

    assert response.status_code == 403


def test_unknown_incident_rejected() -> None:
    assert submit(incident_id="INC-999").status_code == 404


def test_duplicate_request_rejected() -> None:
    assert submit().status_code == 201
    assert submit().status_code == 409


def test_invalid_request_rejected() -> None:
    response = client.post(
        "/tickets",
        headers={"X-Demo-User": "alice"},
        json={
            "incident_id": "oops",
            "reason": "short",
        },
    )

    assert response.status_code == 422


def test_unknown_ticket_rejected() -> None:
    response = client.post(
        "/tickets/TCK-9999/approve",
        headers={"X-Demo-User": "bob"},
    )

    assert response.status_code == 404
