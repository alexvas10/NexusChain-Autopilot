"""Tool functions the agent calls into — the "external system" adapters.

Each function stands in for a real integration (ERP, vendor catalog, shipping/
weather API). Swapping a function body for a real HTTP call is the only change
needed to go from mock to production; the workflow logic above doesn't change.
"""

from app.mock_data import (
    ALTERNATE_ROUTE,
    ERP_ORDERS,
    INVENTORY,
    SHIPPING_ROUTES,
    VENDOR_CATALOG,
    WEATHER,
)


def lookup_inventory(item_name: str, spec: str | None) -> dict | None:
    """Find the inventory SKU matching an item name (+ optional spec)."""
    candidates = [row for row in INVENTORY if row["name"].lower() == item_name.lower().strip()]
    if not candidates:
        return None
    if spec:
        exact = [row for row in candidates if spec.lower().strip() in row["spec"].lower()]
        if exact:
            return exact[0]
        return None  # spec given but doesn't match a known variant -> needs human review
    if len(candidates) == 1:
        return candidates[0]
    return None  # multiple spec variants exist and none was specified -> ambiguous


def lookup_vendor_price(sku: str) -> dict | None:
    """Best (lowest unit price) vendor offer for a SKU, used when stock is insufficient."""
    offers = [row for row in VENDOR_CATALOG if row["sku"] == sku]
    if not offers:
        return None
    return min(offers, key=lambda row: row["unit_price"])


def get_orders_by_shipment(shipment_id: str) -> list[dict]:
    return [order for order in ERP_ORDERS if order["shipment_id"] == shipment_id]


def get_route(route_id: str) -> dict | None:
    return SHIPPING_ROUTES.get(route_id)


def get_alternate_route(current_route_id: str) -> tuple[str, dict] | None:
    alt_id = ALTERNATE_ROUTE.get(current_route_id)
    if not alt_id:
        return None
    return alt_id, SHIPPING_ROUTES[alt_id]


def get_weather(location: str) -> dict:
    return WEATHER.get(location, {"condition": "unknown", "port_delay_days": 0})


def update_manifest_route(shipment_id: str, new_route_id: str) -> int:
    """Mock ERP write: point every order on this shipment at the new route. Returns count updated."""
    updated = 0
    for order in ERP_ORDERS:
        if order["shipment_id"] == shipment_id:
            order["route"] = new_route_id
            updated += 1
    return updated
