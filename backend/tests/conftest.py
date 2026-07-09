"""Shared test setup.

All Qwen calls are stubbed at their usage sites — the suite verifies the workflow,
guardrail, HITL, and API logic deterministically without a network or an API key.
The live-model path is exercised separately (see the demo script / handoff doc).
"""

import copy
import os
import pathlib

# Must be set before any app module import: db.py builds its engine at import time.
os.environ["DATABASE_URL"] = "sqlite:///./test_ops_autopilot.db"
os.environ.setdefault("DASHSCOPE_API_KEY", "test-key-not-used")

import pytest  # noqa: E402

from app import mock_data  # noqa: E402


@pytest.fixture(autouse=True)
def restore_mock_data():
    """update_manifest_route mutates ERP_ORDERS in place; keep tests order-independent."""
    snapshot = copy.deepcopy(mock_data.ERP_ORDERS)
    yield
    mock_data.ERP_ORDERS[:] = snapshot


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    yield
    pathlib.Path("test_ops_autopilot.db").unlink(missing_ok=True)


# --- Canned Qwen responses -------------------------------------------------------

def make_classification(decision="autonomous", summary="test summary", reasoning="test reasoning"):
    return {"decision": decision, "summary": summary, "reasoning": reasoning}


def make_agent_result(
    decision="autonomous",
    recommend_reroute=True,
    summary="storm disrupting shipment",
    reasoning="alternate route is faster",
    trace=None,
):
    return {
        "decision": decision,
        "recommend_reroute": recommend_reroute,
        "summary": summary,
        "reasoning": reasoning,
        "trace": trace
        if trace is not None
        else [
            {
                "tool": "get_orders_by_shipment",
                "arguments": {"shipment_id": "SHIP-7781"},
                "result": [{"order_id": "SO-10432"}, {"order_id": "SO-10433"}],
            }
        ],
    }
