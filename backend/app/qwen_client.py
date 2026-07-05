import json

from openai import OpenAI

from app.config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, QWEN_MODEL

_client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)

_SYSTEM_PROMPT = """You are the exception classifier for an "Ops Autopilot" agent that \
automates business workflows (RFQ quoting, shipment disruption response).

Given a workflow name and a raw inbound request (email text, alert text, etc.), decide \
whether the agent can proceed autonomously or whether it must pause for a human checkpoint.

Route to human_review whenever the request is ambiguous, missing required details \
(e.g. a part is requested without a size/spec, or a monetary decision exceeds normal \
discretion), or carries meaningful financial/operational risk.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{"decision": "autonomous" | "human_review", "summary": "<one sentence summary of the request>", "reasoning": "<one or two sentences explaining the decision>"}
"""


def _chat_json(system_prompt: str, user_content: str) -> dict:
    response = _client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Model occasionally wraps JSON in fences despite instructions; strip and retry once.
        cleaned = raw.strip("`").removeprefix("json").strip()
        return json.loads(cleaned)


def classify_request(workflow: str, text: str) -> dict:
    return _chat_json(_SYSTEM_PROMPT, f"Workflow: {workflow}\n\nRequest:\n{text}")


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
    result = _chat_json(_EXTRACT_ITEMS_PROMPT, text)
    return result.get("items", [])
