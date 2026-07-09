"""Workflow B: disruption response — a Qwen tool-use agent investigates the alert
(ERP orders, routes, weather), then a deterministic layer independently recomputes the
financials and applies the approval guardrail. The model recommends; the arithmetic
that money depends on is never delegated to it.
"""

from app.agent import run_disruption_agent
from app.config import DISRUPTION_COST_APPROVAL_THRESHOLD
from app.tools import (
    get_alternate_route,
    get_orders_by_shipment,
    get_route,
    get_weather,
    update_manifest_route,
)


def process_disruption(shipment_id: str, alert_text: str, location: str | None = None) -> dict:
    agent = run_disruption_agent(shipment_id, alert_text, location)
    classification = {
        "decision": agent["decision"],
        "summary": agent["summary"],
        "reasoning": agent["reasoning"],
    }
    agent_trace = agent.get("trace", [])

    # Deterministic verification layer: recompute affected orders, routes, and the cost
    # delta from source data rather than trusting the agent's account of them.
    orders = get_orders_by_shipment(shipment_id)
    if not orders:
        return {
            "classification": classification,
            "agent_trace": agent_trace,
            "shipment_id": shipment_id,
            "error": f"no orders found for shipment {shipment_id}",
            "needs_human_review": True,
        }

    current_route_id = orders[0]["route"]
    current_route = get_route(current_route_id)
    alt = get_alternate_route(current_route_id)
    weather = get_weather(location) if location else None

    if alt is None:
        return {
            "classification": classification,
            "agent_trace": agent_trace,
            "shipment_id": shipment_id,
            "affected_orders": orders,
            "current_route": {"id": current_route_id, **current_route},
            "error": f"no alternate route configured for {current_route_id}",
            "needs_human_review": True,
        }

    alt_route_id, alt_route = alt
    cost_delta = round(alt_route["cost_per_shipment"] - current_route["cost_per_shipment"], 2)
    time_saved_days = current_route["eta_days"] - alt_route["eta_days"]

    needs_human_review = (
        classification.get("decision") == "human_review"
        or cost_delta > DISRUPTION_COST_APPROVAL_THRESHOLD
    )

    return {
        "classification": classification,
        "agent_trace": agent_trace,
        "recommend_reroute": agent.get("recommend_reroute", False),
        "shipment_id": shipment_id,
        "affected_orders": orders,
        "current_route": {"id": current_route_id, **current_route},
        "recommended_route": {"id": alt_route_id, **alt_route},
        "cost_delta": cost_delta,
        "time_saved_days": time_saved_days,
        "weather": weather,
        "needs_human_review": needs_human_review,
    }


def execute_reroute(shipment_id: str, new_route_id: str) -> str:
    orders = get_orders_by_shipment(shipment_id)
    customers = sorted({order["customer"] for order in orders})
    updated = update_manifest_route(shipment_id, new_route_id)
    return (
        f"Updated manifest for {updated} order(s) on {shipment_id} to route {new_route_id}. "
        f"Notified customers: {', '.join(customers)}."
    )
