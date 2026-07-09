"""End-to-end API tests over the FastAPI app with all Qwen calls stubbed."""

import json

import pytest
from fastapi.testclient import TestClient
from conftest import make_agent_result, make_classification

import app.main as main_module
from app.db import Base, engine
from app.workflows import disruption, rfq


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Don't touch the filesystem/OSS during API tests.
    monkeypatch.setattr(main_module, "store_payload", lambda key, content: f"test://{key}")
    with TestClient(main_module.app) as c:
        yield c


@pytest.fixture
def stub_ambiguous_rfq(monkeypatch):
    monkeypatch.setattr(
        rfq,
        "classify_request",
        lambda w, t: make_classification("human_review", "50 bolts, no spec", "missing bolt spec"),
    )
    monkeypatch.setattr(
        rfq,
        "extract_line_items",
        lambda t: [{"item_name": "heavy-duty bolt", "spec": None, "qty": 50, "spec_complete": False}],
    )


@pytest.fixture
def stub_disruption_agent(monkeypatch):
    monkeypatch.setattr(
        disruption, "run_disruption_agent", lambda s, a, l: make_agent_result("human_review")
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_intake_rejects_non_rfq_workflow(client):
    resp = client.post("/intake", json={"workflow": "disruption", "text": "storm"})
    assert resp.status_code == 400


def test_ambiguous_rfq_creates_pending_exception(client, stub_ambiguous_rfq):
    resp = client.post("/intake", json={"workflow": "rfq", "text": "50 heavy-duty bolts ASAP"})
    body = resp.json()

    assert resp.status_code == 200
    assert body["decision"] == "human_review"
    assert body["quote"]["unresolved_items"][0]["item_name"] == "heavy-duty bolt"

    pending = client.get("/exceptions", params={"status": "pending"}).json()
    assert len(pending) == 1
    assert pending[0]["workflow"] == "rfq"


def test_autonomous_rfq_is_audited_as_approved(client, monkeypatch):
    monkeypatch.setattr(rfq, "classify_request", lambda w, t: make_classification("autonomous"))
    monkeypatch.setattr(
        rfq,
        "extract_line_items",
        lambda t: [{"item_name": "gasket", "spec": "Viton, 2in", "qty": 10, "spec_complete": True}],
    )
    resp = client.post("/intake", json={"workflow": "rfq", "text": "10 viton 2in gaskets"})

    assert resp.json()["decision"] == "autonomous"
    assert client.get("/exceptions", params={"status": "pending"}).json() == []
    approved = client.get("/exceptions", params={"status": "approved"}).json()
    assert len(approved) == 1  # audited even though no human ever saw it
    assert "Quote finalized" in approved[0]["action_log"]


def test_disruption_webhook_returns_delta_and_trace(client, stub_disruption_agent):
    resp = client.post(
        "/webhooks/disruption",
        json={"shipment_id": "SHIP-7781", "alert_text": "Severe winter storm", "location": "Chicago, IL"},
    )
    body = resp.json()

    assert body["decision"] == "human_review"
    assert body["cost_delta"] == 1200.0
    assert body["recommended_route"]["id"] == "ROUTE-AIR-EXPEDITE"
    assert body["agent_trace"][0]["tool"] == "get_orders_by_shipment"


def test_approving_disruption_executes_reroute(client, stub_disruption_agent):
    exc_id = client.post(
        "/webhooks/disruption",
        json={"shipment_id": "SHIP-7781", "alert_text": "Severe winter storm", "location": "Chicago, IL"},
    ).json()["exception_id"]

    resolved = client.post(
        f"/exceptions/{exc_id}/decision", json={"action": "approve", "notes": "go ahead"}
    ).json()

    assert resolved["status"] == "approved"
    assert "Meridian Manufacturing" in resolved["action_log"]
    assert "Bluepoint Robotics" in resolved["action_log"]


def test_rejecting_rfq_drafts_customer_reply(client, stub_ambiguous_rfq, monkeypatch):
    draft = {"subject": "Quick question about your bolt order", "body": "Which thread size do you need?"}
    monkeypatch.setattr(main_module, "draft_customer_reply", lambda p, u, n: draft)

    exc_id = client.post(
        "/intake", json={"workflow": "rfq", "text": "50 heavy-duty bolts ASAP"}
    ).json()["exception_id"]
    resolved = client.post(
        f"/exceptions/{exc_id}/decision", json={"action": "reject", "notes": "ask for thread size"}
    ).json()

    assert resolved["status"] == "rejected"
    assert "clarification email drafted" in resolved["action_log"]
    assert json.loads(resolved["details"])["customer_reply_draft"] == draft


def test_dashboard_renders_pending_and_resolved(client, stub_ambiguous_rfq, stub_disruption_agent, monkeypatch):
    client.post("/intake", json={"workflow": "rfq", "text": "50 heavy-duty bolts ASAP"})
    exc_id = client.post(
        "/webhooks/disruption",
        json={"shipment_id": "SHIP-7781", "alert_text": "Severe winter storm", "location": "Chicago, IL"},
    ).json()["exception_id"]

    page = client.get("/dashboard").text
    assert "50 heavy-duty bolts ASAP" in page
    assert "Agent investigation" in page  # tool-call trace is visible to the reviewer

    client.post(f"/exceptions/{exc_id}/decision", json={"action": "approve"})
    page = client.get("/dashboard").text
    assert "Updated manifest" in page  # action log surfaces on the resolved card


def test_decision_validation(client, stub_ambiguous_rfq):
    exc_id = client.post(
        "/intake", json={"workflow": "rfq", "text": "50 heavy-duty bolts ASAP"}
    ).json()["exception_id"]

    assert client.post(f"/exceptions/{exc_id}/decision", json={"action": "maybe"}).status_code == 400
    assert client.post("/exceptions/9999/decision", json={"action": "approve"}).status_code == 404
