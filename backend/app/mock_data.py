"""Deterministic mock fixtures standing in for ERP / vendor / shipping / weather systems.

Real deployment would swap these for calls into an actual ERP (e.g. SAP/NetSuite),
a vendor-catalog API, and a shipping/weather provider. Kept in-memory and mutable
(dicts, not tuples) so the disruption workflow can "update the manifest" during a demo.
"""

# --- Workflow A (RFQ) fixtures --------------------------------------------------

INVENTORY = [
    {"sku": "BOLT-HD-M8", "name": "heavy-duty bolt", "spec": "M8 x 40mm", "stock": 4200, "unit_cost": 0.42},
    {"sku": "BOLT-HD-M10", "name": "heavy-duty bolt", "spec": "M10 x 50mm", "stock": 1800, "unit_cost": 0.61},
    {"sku": "BOLT-HD-M12", "name": "heavy-duty bolt", "spec": "M12 x 60mm", "stock": 600, "unit_cost": 0.89},
    {"sku": "BRKT-STD", "name": "steel bracket", "spec": "standard L-bracket", "stock": 3000, "unit_cost": 1.15},
    {"sku": "GSKT-VITON", "name": "gasket", "spec": "Viton, 2in", "stock": 950, "unit_cost": 2.30},
    {"sku": "HOSE-BRD-25", "name": "braided hose", "spec": "25ft, stainless", "stock": 210, "unit_cost": 18.75},
]

VENDOR_CATALOG = [
    {"vendor": "Titan Fasteners Co.", "sku": "BOLT-HD-M8", "unit_price": 0.55, "lead_time_days": 5},
    {"vendor": "Titan Fasteners Co.", "sku": "BOLT-HD-M10", "unit_price": 0.78, "lead_time_days": 5},
    {"vendor": "Titan Fasteners Co.", "sku": "BOLT-HD-M12", "unit_price": 1.05, "lead_time_days": 7},
    {"vendor": "Summit Industrial Supply", "sku": "BRKT-STD", "unit_price": 1.40, "lead_time_days": 3},
    {"vendor": "Summit Industrial Supply", "sku": "GSKT-VITON", "unit_price": 2.75, "lead_time_days": 4},
    {"vendor": "Coastal Hose & Fitting", "sku": "HOSE-BRD-25", "unit_price": 21.00, "lead_time_days": 10},
]

# --- Workflow B (disruption response) fixtures ---------------------------------

ERP_ORDERS = [
    {
        "order_id": "SO-10432",
        "customer": "Meridian Manufacturing",
        "shipment_id": "SHIP-7781",
        "items": [{"sku": "GSKT-VITON", "qty": 500}],
        "destination": "Chicago, IL",
        "status": "in_transit",
        "route": "ROUTE-OCEAN-STD",
    },
    {
        "order_id": "SO-10433",
        "customer": "Bluepoint Robotics",
        "shipment_id": "SHIP-7781",
        "items": [{"sku": "HOSE-BRD-25", "qty": 40}],
        "destination": "Chicago, IL",
        "status": "in_transit",
        "route": "ROUTE-OCEAN-STD",
    },
    {
        "order_id": "SO-10440",
        "customer": "Harborview Foods",
        "shipment_id": "SHIP-9002",
        "items": [{"sku": "BRKT-STD", "qty": 1200}],
        "destination": "Seattle, WA",
        "status": "in_transit",
        "route": "ROUTE-TRUCK-STD",
    },
]

SHIPPING_ROUTES = {
    "ROUTE-OCEAN-STD": {
        "mode": "ocean",
        "cost_per_shipment": 2400.00,
        "eta_days": 21,
        "carrier": "Pacific Star Lines",
    },
    "ROUTE-AIR-EXPEDITE": {
        "mode": "air",
        "cost_per_shipment": 3600.00,
        "eta_days": 4,
        "carrier": "SkyFreight Express",
    },
    "ROUTE-TRUCK-STD": {
        "mode": "truck",
        "cost_per_shipment": 1100.00,
        "eta_days": 6,
        "carrier": "Continental Trucking",
    },
    "ROUTE-TRUCK-EXPEDITE": {
        "mode": "truck",
        "cost_per_shipment": 1900.00,
        "eta_days": 2,
        "carrier": "Continental Trucking",
    },
}

# Alternate route for a given disrupted route: which route to switch to.
ALTERNATE_ROUTE = {
    "ROUTE-OCEAN-STD": "ROUTE-AIR-EXPEDITE",
    "ROUTE-TRUCK-STD": "ROUTE-TRUCK-EXPEDITE",
}

WEATHER = {
    "Chicago, IL": {"condition": "severe winter storm", "port_delay_days": 6},
    "Seattle, WA": {"condition": "clear", "port_delay_days": 0},
    "Los Angeles, CA": {"condition": "high winds", "port_delay_days": 2},
}
