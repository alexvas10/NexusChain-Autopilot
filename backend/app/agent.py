"""Qwen function-calling agent loop.

`run_agent` is a generic tool-use loop over DashScope's OpenAI-compatible `tools` API:
the model decides which tools to call and in what order; we execute them, feed results
back, and capture every step in a trace that is persisted with the exception record so
a reviewer can audit exactly what the agent looked at before it decided.

`run_disruption_agent` is the concrete agent for the disruption-response workflow: it
investigates a shipment alert with ERP/routing/weather tools, then emits a structured
decision. The deterministic guardrails (cost recomputation, approval threshold) live in
`app.workflows.disruption` — the model recommends, it does not get to do the arithmetic
that money depends on.
"""

import json
import logging
from typing import Callable

from app.qwen_client import chat_completion, parse_json_reply
from app.tools import get_alternate_route, get_orders_by_shipment, get_route, get_weather

logger = logging.getLogger(__name__)

MAX_AGENT_TURNS = 8


class AgentLoopError(Exception):
    """The agent loop could not produce a final structured answer."""


def run_agent(
    system_prompt: str,
    user_content: str,
    tool_specs: list[dict],
    tool_impls: dict[str, Callable],
    max_turns: int = MAX_AGENT_TURNS,
) -> tuple[dict, list[dict]]:
    """Run a tool-use loop until the model returns a final JSON answer.

    Returns (final_answer, trace). Trace entries record each tool invocation:
    {"tool": name, "arguments": {...}, "result": <return value>}.
    Raises AgentLoopError if the turn budget is exhausted or the final reply
    isn't valid JSON — callers are expected to fail safe to human review.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    trace: list[dict] = []

    for _ in range(max_turns):
        message = chat_completion(messages, tools=tool_specs)

        if not message.tool_calls:
            try:
                return parse_json_reply(message.content or ""), trace
            except (json.JSONDecodeError, ValueError) as exc:
                raise AgentLoopError(f"final reply was not valid JSON: {exc}") from exc

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ],
            }
        )

        for call in message.tool_calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            impl = tool_impls.get(name)
            if impl is None:
                result: object = {"error": f"unknown tool: {name}"}
            else:
                try:
                    result = impl(**arguments)
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}

            trace.append({"tool": name, "arguments": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

    raise AgentLoopError(f"no final answer after {max_turns} turns")


# --- Disruption-response agent ---------------------------------------------------

def _tool_get_alternate_route(current_route_id: str):
    # Adapt the (route_id, route) tuple to a JSON-friendly shape for the model.
    alt = get_alternate_route(current_route_id)
    if alt is None:
        return None
    alt_id, route = alt
    return {"route_id": alt_id, **route}


_DISRUPTION_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_orders_by_shipment",
            "description": "Look up all ERP sales orders travelling on a shipment, "
            "including customer, destination, and current route id.",
            "parameters": {
                "type": "object",
                "properties": {"shipment_id": {"type": "string"}},
                "required": ["shipment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_route",
            "description": "Get a shipping route's mode, carrier, cost per shipment, and ETA in days.",
            "parameters": {
                "type": "object",
                "properties": {"route_id": {"type": "string"}},
                "required": ["route_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alternate_route",
            "description": "Get the configured fallback route for a disrupted route, "
            "or null if none exists.",
            "parameters": {
                "type": "object",
                "properties": {"current_route_id": {"type": "string"}},
                "required": ["current_route_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Current weather condition and expected port delay (days) at a location.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    },
]

_DISRUPTION_TOOL_IMPLS = {
    "get_orders_by_shipment": get_orders_by_shipment,
    "get_route": get_route,
    "get_alternate_route": _tool_get_alternate_route,
    "get_weather": get_weather,
}

_DISRUPTION_SYSTEM_PROMPT = """You are the disruption-response agent for an "Ops \
Autopilot" system at an industrial supplier. A shipment/logistics disruption alert has \
arrived. Investigate before you decide:

1. Look up which orders are on the shipment and what route they are on.
2. Check the current route and the configured alternate route.
3. If a location is given, check the weather there to gauge how real the disruption is.

Then decide whether rerouting to the alternate route is warranted, and whether the \
situation is routine enough to proceed autonomously or ambiguous/risky enough to need a \
human checkpoint. Route to human_review when the alert is vague, the shipment is \
unknown, no alternate route exists, or the operational/financial stakes are meaningful.

After investigating, respond with ONLY a JSON object, no prose, no markdown fences:
{"decision": "autonomous" | "human_review", "recommend_reroute": true | false, "summary": "<one sentence summary of the disruption and affected orders>", "reasoning": "<two or three sentences citing what the tools showed>"}
"""


def run_disruption_agent(shipment_id: str, alert_text: str, location: str | None) -> dict:
    """Investigate a disruption alert via the tool loop; fail safe to human_review.

    Returns {"decision", "recommend_reroute", "summary", "reasoning", "trace"}.
    """
    user_content = (
        f"Shipment: {shipment_id}\n"
        f"Reported location: {location or 'not given'}\n\n"
        f"Alert:\n{alert_text}"
    )
    try:
        answer, trace = run_agent(
            _DISRUPTION_SYSTEM_PROMPT,
            user_content,
            _DISRUPTION_TOOL_SPECS,
            _DISRUPTION_TOOL_IMPLS,
        )
        return {
            "decision": answer.get("decision", "human_review"),
            "recommend_reroute": bool(answer.get("recommend_reroute", False)),
            "summary": answer.get("summary", alert_text[:200]),
            "reasoning": answer.get("reasoning", ""),
            "trace": trace,
        }
    except Exception as exc:
        logger.exception("disruption agent loop failed; failing safe to human_review")
        return {
            "decision": "human_review",
            "recommend_reroute": False,
            "summary": alert_text[:200],
            "reasoning": f"Agent investigation unavailable ({type(exc).__name__}); "
            "routed to human review as a fail-safe.",
            "trace": [],
        }
