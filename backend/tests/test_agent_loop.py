"""Tests for the generic Qwen tool-use loop, driven by a scripted fake model."""

import json
from types import SimpleNamespace

import pytest

from app import agent


def fake_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def fake_tool_call(call_id, name, arguments: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def scripted_model(monkeypatch, replies: list):
    """Replace the live model with a queue of canned assistant messages."""
    queue = list(replies)
    transcript = []

    def fake_chat(messages, tools=None):
        transcript.append([dict(m) for m in messages])
        return queue.pop(0)

    monkeypatch.setattr(agent, "chat_completion", fake_chat)
    return transcript


def test_loop_executes_tools_and_returns_final_json(monkeypatch):
    transcript = scripted_model(
        monkeypatch,
        [
            fake_message(tool_calls=[fake_tool_call("c1", "get_orders_by_shipment", {"shipment_id": "SHIP-7781"})]),
            fake_message(content='{"decision": "human_review", "recommend_reroute": true, "summary": "s", "reasoning": "r"}'),
        ],
    )

    answer, trace = agent.run_agent(
        "system", "user", agent._DISRUPTION_TOOL_SPECS, agent._DISRUPTION_TOOL_IMPLS
    )

    assert answer["decision"] == "human_review"
    assert len(trace) == 1
    assert trace[0]["tool"] == "get_orders_by_shipment"
    assert len(trace[0]["result"]) == 2  # both SHIP-7781 orders, from the real tool impl

    # The tool result was fed back to the model as a tool-role message.
    final_turn = transcript[1]
    assert final_turn[-1]["role"] == "tool"
    assert "SO-10432" in final_turn[-1]["content"]


def test_unknown_tool_is_reported_not_fatal(monkeypatch):
    scripted_model(
        monkeypatch,
        [
            fake_message(tool_calls=[fake_tool_call("c1", "launch_missiles", {})]),
            fake_message(content='{"decision": "human_review"}'),
        ],
    )

    answer, trace = agent.run_agent("system", "user", [], {})

    assert trace[0]["result"] == {"error": "unknown tool: launch_missiles"}
    assert answer["decision"] == "human_review"


def test_tool_exception_is_captured_in_trace(monkeypatch):
    def exploding_tool(**kwargs):
        raise RuntimeError("ERP timeout")

    scripted_model(
        monkeypatch,
        [
            fake_message(tool_calls=[fake_tool_call("c1", "get_route", {"route_id": "X"})]),
            fake_message(content='{"decision": "human_review"}'),
        ],
    )

    _, trace = agent.run_agent("system", "user", [], {"get_route": exploding_tool})
    assert trace[0]["result"] == {"error": "RuntimeError: ERP timeout"}


def test_non_json_final_reply_raises(monkeypatch):
    scripted_model(monkeypatch, [fake_message(content="I think you should reroute!")])
    with pytest.raises(agent.AgentLoopError):
        agent.run_agent("system", "user", [], {})


def test_turn_budget_exhaustion_raises(monkeypatch):
    endless = [
        fake_message(tool_calls=[fake_tool_call(f"c{i}", "get_weather", {"location": "Chicago, IL"})])
        for i in range(agent.MAX_AGENT_TURNS)
    ]
    scripted_model(monkeypatch, endless)
    with pytest.raises(agent.AgentLoopError):
        agent.run_agent("system", "user", [], agent._DISRUPTION_TOOL_IMPLS)


def test_disruption_agent_fails_safe_to_human_review(monkeypatch):
    def broken_chat(messages, tools=None):
        raise ConnectionError("DashScope unreachable")

    monkeypatch.setattr(agent, "chat_completion", broken_chat)
    result = agent.run_disruption_agent("SHIP-7781", "Storm alert", "Chicago, IL")

    assert result["decision"] == "human_review"
    assert result["recommend_reroute"] is False
    assert "fail-safe" in result["reasoning"]
