"""Qwen Cloud (DashScope) client layer.

All model access goes through `chat_completion`, which sets an explicit timeout and
retries once on transient failure. Every public helper is fail-safe: if the model is
unreachable or returns something unparseable, the caller gets a conservative
`human_review` decision (or an empty extraction) with the error captured in the
reasoning — the pipeline degrades to a human checkpoint instead of a 500.
"""

import json
import logging

from openai import OpenAI

from app.config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, QWEN_MODEL

logger = logging.getLogger(__name__)

_client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    timeout=30.0,
    max_retries=1,
)


def chat_completion(messages: list[dict], tools: list[dict] | None = None):
    """Single Qwen chat call; returns the raw assistant message (may carry tool_calls)."""
    kwargs = {"model": QWEN_MODEL, "messages": messages, "temperature": 0}
    if tools:
        kwargs["tools"] = tools
    response = _client.chat.completions.create(**kwargs)
    return response.choices[0].message


def parse_json_reply(raw: str) -> dict:
    """Parse a JSON-only model reply, tolerating markdown fences."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip("`").removeprefix("json").strip()
        return json.loads(cleaned)


def _chat_json(system_prompt: str, user_content: str) -> dict:
    message = chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )
    return parse_json_reply(message.content)


_SYSTEM_PROMPT = """You are the exception classifier for an "NexusChain Autopilot" agent that \
automates business workflows (RFQ quoting, shipment disruption response).

Given a workflow name and a raw inbound request (email text, alert text, etc.), decide \
whether the agent can proceed autonomously or whether it must pause for a human checkpoint.

Route to human_review whenever the request is ambiguous, missing required details \
(e.g. a part is requested without a size/spec, or a monetary decision exceeds normal \
discretion), or carries meaningful financial/operational risk.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{"decision": "autonomous" | "human_review", "summary": "<one sentence summary of the request>", "reasoning": "<one or two sentences explaining the decision>"}
"""


def classify_request(workflow: str, text: str) -> dict:
    try:
        return _chat_json(_SYSTEM_PROMPT, f"Workflow: {workflow}\n\nRequest:\n{text}")
    except Exception as exc:  # fail safe: an unreachable model must never auto-approve
        logger.exception("classify_request failed; failing safe to human_review")
        return {
            "decision": "human_review",
            "summary": text[:200],
            "reasoning": f"Automatic classification unavailable ({type(exc).__name__}); "
            "routed to human review as a fail-safe.",
        }


_EXTRACT_ITEMS_PROMPT = """You extract structured line items from a messy RFQ (request \
for quote) email or note.

For each distinct item requested, produce an object with:
- "item_name": the base product name, normalized to lowercase (e.g. "heavy-duty bolt", \
"steel bracket", "gasket", "braided hose") — use the closest matching common industrial \
part name, not the customer's exact wording.
- "spec": the size/material/variant detail if the customer gave one (e.g. "M10 x 50mm", \
"Viton, 2in"), otherwise null.
- "qty": integer quantity requested.
- "spec_complete": true if the request contains enough detail (size/spec) to source an \
exact part with no ambiguity, false if a spec is required for this item type but missing \
or vague.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{"items": [{"item_name": "...", "spec": "..." | null, "qty": 0, "spec_complete": true | false}]}
"""


def extract_line_items(text: str) -> list[dict]:
    try:
        result = _chat_json(_EXTRACT_ITEMS_PROMPT, text)
        return result.get("items", [])
    except Exception:
        logger.exception("extract_line_items failed; returning no items (forces human review)")
        return []


_REPLY_PROMPT = """You draft a short, professional reply email from an industrial supplier \
to a customer, about their recent request for quote.

You are given the customer's original request, the list of items we could not price \
(with the reason each is unresolved), and an optional internal note from the human \
reviewer. Ask the customer for exactly the missing details, briefly and politely. If the \
reviewer's note gives a reason the quote was declined, communicate it tactfully instead.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{"subject": "<email subject>", "body": "<email body, plain text, max ~120 words>"}
"""


def draft_customer_reply(
    original_request: str, unresolved_items: list[dict], reviewer_notes: str | None
) -> dict | None:
    """Draft a clarification/decline email for an RFQ the human reviewer rejected.

    Returns None if the model is unavailable — the caller records that drafting failed
    rather than blocking the decision itself.
    """
    context = {
        "original_request": original_request,
        "unresolved_items": unresolved_items,
        "reviewer_notes": reviewer_notes or "",
    }
    try:
        return _chat_json(_REPLY_PROMPT, json.dumps(context, indent=2))
    except Exception:
        logger.exception("draft_customer_reply failed; skipping draft")
        return None
