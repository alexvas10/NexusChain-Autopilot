"""Workflow B: disruption response — given a shipment/logistics alert, find affected
orders, evaluate an alternate route, and price the cost delta of rerouting.
"""

from app.config import DISRUPTION_COST_APPROVAL_THRESHOLD
from app.qwen_client import classify_request
from app.tools import (
    get_alternate_route,
    get_orders_by_shipment,
    get_route,
    get_weather,
    update_manifest_route,
)


def process_disruption(shipment_id: str, alert_text: str, location: str | None = None) -> dict:
    classification = classify_request("disruption", alert_text)
    orders = get_orders_by_shipment(shipment_id)
    if not orders:
        return {
            "classification": classification,
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
