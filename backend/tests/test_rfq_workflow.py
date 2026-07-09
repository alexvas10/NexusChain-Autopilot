from conftest import make_classification

from app.workflows import rfq


def test_prices_in_stock_items(monkeypatch):
    monkeypatch.setattr(rfq, "classify_request", lambda w, t: make_classification("autonomous"))
    monkeypatch.setattr(
        rfq,
        "extract_line_items",
        lambda t: [
            {"item_name": "gasket", "spec": "Viton, 2in", "qty": 100, "spec_complete": True},
            {"item_name": "steel bracket", "spec": "standard L-bracket", "qty": 200, "spec_complete": True},
        ],
    )
    result = rfq.process_rfq("100 viton gaskets and 200 brackets")

    assert result["needs_human_review"] is False
    assert result["unresolved_items"] == []
    assert len(result["line_items"]) == 2
    gasket = result["line_items"][0]
    assert gasket["sku"] == "GSKT-VITON"
    assert gasket["unit_price"] == round(2.30 * 1.35, 2)
    assert gasket["line_total"] == round(gasket["unit_price"] * 100, 2)
    assert result["subtotal"] == round(
        sum(li["line_total"] for li in result["line_items"]), 2
    )


def test_missing_spec_forces_review(monkeypatch):
    monkeypatch.setattr(rfq, "classify_request", lambda w, t: make_classification("autonomous"))
    monkeypatch.setattr(
        rfq,
        "extract_line_items",
        lambda t: [{"item_name": "heavy-duty bolt", "spec": None, "qty": 50, "spec_complete": False}],
    )
    result = rfq.process_rfq("50 heavy-duty bolts ASAP")

    assert result["needs_human_review"] is True
    assert result["line_items"] == []
    assert result["unresolved_items"][0]["reason"] == "missing required size/spec"


def test_insufficient_stock_falls_back_to_vendor(monkeypatch):
    monkeypatch.setattr(rfq, "classify_request", lambda w, t: make_classification("autonomous"))
    monkeypatch.setattr(
        rfq,
        "extract_line_items",
        lambda t: [{"item_name": "braided hose", "spec": "25ft, stainless", "qty": 500, "spec_complete": True}],
    )
    result = rfq.process_rfq("500 braided hoses")

    line = result["line_items"][0]
    assert line["unit_price"] == round(21.00 * 1.15, 2)  # vendor price + vendor markup
    assert "Coastal Hose & Fitting" in line["source"]


def test_classifier_human_review_wins_even_if_priced(monkeypatch):
    monkeypatch.setattr(rfq, "classify_request", lambda w, t: make_classification("human_review"))
    monkeypatch.setattr(
        rfq,
        "extract_line_items",
        lambda t: [{"item_name": "gasket", "spec": "Viton, 2in", "qty": 10, "spec_complete": True}],
    )
    result = rfq.process_rfq("10 gaskets, and also cancel my other order??")

    assert result["needs_human_review"] is True
    assert len(result["line_items"]) == 1  # still priced, just gated


def test_empty_extraction_forces_review(monkeypatch):
    # Covers both a nonsense request and a failed/unavailable extraction call.
    monkeypatch.setattr(rfq, "classify_request", lambda w, t: make_classification("autonomous"))
    monkeypatch.setattr(rfq, "extract_line_items", lambda t: [])
    result = rfq.process_rfq("hello?")

    assert result["needs_human_review"] is True
    assert result["line_items"] == []
