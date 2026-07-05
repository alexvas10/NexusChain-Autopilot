"""Slack interactive-button HITL surface for the disruption workflow.

Posts to a real Slack Incoming Webhook when SLACK_WEBHOOK_URL is configured;
otherwise logs the message so the flow is fully exercisable in local/dev
before Slack credentials exist.
"""

import httpx

from app.config import SLACK_WEBHOOK_URL


def send_approval_message(exception_id: int, summary: str, cost_delta: float) -> str:
    text = (
        f":rotating_light: *Disruption exception #{exception_id}*\n"
        f"{summary}\n"
        f"Estimated cost delta: *${cost_delta:,.2f}*\n"
        f"Approve or reject at the Ops Autopilot dashboard: /dashboard#{exception_id}"
    )
    if SLACK_WEBHOOK_URL:
        httpx.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
    else:
        print(f"[slack:dev-stub] {text}")
    return text
