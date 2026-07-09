from conftest import make_agent_result

from app import mock_data
from app.workflows import disruption


def test_cost_delta_computed_deterministically(monkeypatch):
    monkeypatch.setattr(
        disruption, "run_disruption_agent", lambda s, a, l: make_agent_result("autonomous")
    )
    result = disruption.process_disruption("SHIP-7781", "Severe winter storm", "Chicago, IL")

    assert result["cost_delta"] == 1200.0  # air 3600 - ocean 2400, recomputed, not model-quoted
    assert result["time_saved_days"] == 17
    assert result["recommended_route"]["id"] == "ROUTE-AIR-EXPEDITE"
    assert [o["order_id"] for o in result["affected_orders"]] == ["SO-10432", "SO-10433"]
    assert result["weather"]["condition"] == "severe winter storm"
    assert result["agent_trace"][0]["tool"] == "get_orders_by_shipment"


def test_cost_threshold_guardrail_overrides_autonomous_agent(monkeypatch):
    # Agent says autonomous, but $1200 > $200 threshold: the deterministic guardrail wins.
    monkeypatch.setattr(
        disruption, "run_disruption_agent", lambda s, a, l: make_agent_result("autonomous")
    )
    result = disruption.process_disruption("SHIP-7781", "Severe winter storm", "Chicago, IL")
    assert result["needs_human_review"] is True

    monkeypatch.setattr(disruption, "DISRUPTION_COST_APPROVAL_THRESHOLD", 5000.0)
    result = disruption.process_disruption("SHIP-7781", "Severe winter storm", "Chicago, IL")
    assert result["needs_human_review"] is False


def test_agent_human_review_wins_below_threshold(monkeypatch):
    monkeypatch.setattr(disruption, "DISRUPTION_COST_APPROVAL_THRESHOLD", 5000.0)
    monkeypatch.setattr(
        disruption, "run_disruption_agent", lambda s, a, l: make_agent_result("human_review")
    )
    result = disruption.process_disruption("SHIP-7781", "Vague rumor of a delay", "Chicago, IL")
    assert result["needs_human_review"] is True


def test_unknown_shipment_forces_review(monkeypatch):
    monkeypatch.setattr(
        disruption, "run_disruption_agent", lambda s, a, l: make_agent_result("autonomous")
    )
    result = disruption.process_disruption("SHIP-0000", "Storm", "Chicago, IL")

    assert result["needs_human_review"] is True
    assert "no orders found" in result["error"]


def test_execute_reroute_updates_manifest_and_names_customers():
    log = disruption.execute_reroute("SHIP-7781", "ROUTE-AIR-EXPEDITE")

    assert "2 order(s)" in log
    assert "Meridian Manufacturing" in log and "Bluepoint Robotics" in log
    routes = {o["route"] for o in mock_data.ERP_ORDERS if o["shipment_id"] == "SHIP-7781"}
    assert routes == {"ROUTE-AIR-EXPEDITE"}
