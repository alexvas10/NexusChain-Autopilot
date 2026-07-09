"""Workflow A: RFQ intake — parse a messy quote request, price it against inventory
and the vendor catalog, and flag anything ambiguous for human clarification.
"""

from app.qwen_client import classify_request, extract_line_items
from app.tools import lookup_inventory, lookup_vendor_price

# Customer-facing markup over internal cost. Real deployment would pull this from a
# pricing engine / margin policy rather than a flat constant.
_STOCK_MARKUP = 1.35
_VENDOR_MARKUP = 1.15


def process_rfq(text: str) -> dict:
    classification = classify_request("rfq", text)
    raw_items = extract_line_items(text)

    resolved_items = []
    unresolved_items = []
    subtotal = 0.0

    for item in raw_items:
        name = item.get("item_name", "")
        spec = item.get("spec")
        qty = item.get("qty", 0)
        spec_complete = item.get("spec_complete", False)

        inv = lookup_inventory(name, spec) if spec_complete else None
        if inv is None:
            reason = (
                "spec doesn't match a known part variant"
                if spec_complete
                else "missing required size/spec"
            )
            unresolved_items.append({**item, "reason": reason})
            continue

        if inv["stock"] >= qty:
            unit_price = round(inv["unit_cost"] * _STOCK_MARKUP, 2)
            source = "in_stock"
        else:
            vendor = lookup_vendor_price(inv["sku"])
            if vendor is None:
                unresolved_items.append(
                    {**item, "reason": f"insufficient stock and no vendor source for {inv['sku']}"}
                )
                continue
            unit_price = round(vendor["unit_price"] * _VENDOR_MARKUP, 2)
            source = f"vendor: {vendor['vendor']} (lead time {vendor['lead_time_days']}d)"

        line_total = round(unit_price * qty, 2)
        subtotal += line_total
        resolved_items.append(
            {
                "item_name": name,
                "spec": spec,
                "qty": qty,
                "sku": inv["sku"],
                "unit_price": unit_price,
                "line_total": line_total,
                "source": source,
            }
        )

    # No extractable items means either an empty request or a failed extraction call —
    # either way a human should look before a customer gets silence.
    needs_human_review = (
        classification.get("decision") == "human_review"
        or bool(unresolved_items)
        or not raw_items
    )

    return {
        "classification": classification,
        "line_items": resolved_items,
        "unresolved_items": unresolved_items,
        "subtotal": round(subtotal, 2),
        "needs_human_review": needs_human_review,
    }
