# Ops Autopilot — backend

Track 4 "Ops Autopilot" project: a shared agent core (Qwen-based exception classifier,
exception queue via SQLAlchemy, audit trail) with two pluggable workflow playbooks:

- **Workflow A — RFQ intake** (`app/workflows/rfq.py`): parses a free-text quote request
  into line items via Qwen, prices each against mock inventory/vendor-catalog tools
  (`app/tools.py`, fixtures in `app/mock_data.py`), and routes anything with a missing or
  unmatched spec to human review.
- **Workflow B — disruption response** (`app/workflows/disruption.py`): given a shipment
  alert, looks up affected ERP orders and an alternate shipping route, computes the cost
  delta, and requires human approval (dashboard or Slack) above a cost threshold or when
  Qwen flags real risk. Approval triggers `execute_reroute` (mock manifest update +
  customer notice); a Slack Incoming Webhook is used if `SLACK_WEBHOOK_URL` is set,
  otherwise messages are logged locally (`app/slack_client.py`).

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in DASHSCOPE_API_KEY once Qwen Cloud signup is done
```

## Run locally

```bash
uvicorn app.main:app --reload
```

- `GET /health` — liveness check
- `POST /intake` — `{"workflow": "rfq", "text": "..."}` → RFQ intake only; parses, prices,
  and either auto-approves (`quote` in the response) or files a pending exception
- `POST /webhooks/disruption` — `{"shipment_id": "...", "alert_text": "...", "location": "..."}`
  → disruption workflow; returns the recommended route/cost delta and either auto-executes
  the reroute or files a pending exception (and posts to Slack if configured)
- `GET /exceptions` — list exceptions (JSON), optional `?status=pending`
- `POST /exceptions/{id}/decision` — `{"action": "approve"|"reject", "notes": "..."}` →
  also runs the workflow's post-decision action (finalize quote / execute reroute)
- `GET /dashboard` — HTML page to review/approve/reject pending exceptions, with
  workflow-specific detail (priced line items, or affected orders + route cost delta)

## Try it end-to-end (once DASHSCOPE_API_KEY is set)

```bash
curl -X POST localhost:8000/intake \
  -H "Content-Type: application/json" \
  -d '{"workflow": "rfq", "text": "I need 50 heavy-duty bolts, ship ASAP"}'

curl -X POST localhost:8000/webhooks/disruption \
  -H "Content-Type: application/json" \
  -d '{"shipment_id": "SHIP-7781", "alert_text": "Severe winter storm hitting the Chicago port", "location": "Chicago, IL"}'
```

The RFQ call should come back with `decision: "human_review"` (missing bolt size/spec)
and an `exception_id`; the disruption call should come back with a `cost_delta` of
`1200.0` and `decision: "human_review"` (exceeds the cost threshold). Open
`http://localhost:8000/dashboard` to see both and approve/reject them.

Until a real `DASHSCOPE_API_KEY` is set, the workflow/tool logic (pricing, routing, HITL
queue, dashboard, post-approval execution) has been verified locally by monkeypatching
the two Qwen calls (`classify_request`, `extract_line_items`) with canned responses —
see the progress log in the project handoff doc for what was checked.

## Deploying

See `DEPLOY.md` for the Alibaba Cloud runbook (RDS/PolarDB, OSS bucket, ACR + ECS). A
`Dockerfile` is included and has been verified locally (builds, boots, serves `/health`
and `/dashboard`); the Postgres path has also been verified end-to-end against a real
local Postgres container via the `psycopg3` driver (`postgresql+psycopg://...` — note the
driver prefix, plain `postgresql://` will fail since psycopg2 isn't installed).

## Not yet built (next steps per the plan)

- A real Qwen API call (blocked on `DASHSCOPE_API_KEY` — see handoff doc)
- The actual Alibaba Cloud deployment (RDS/OSS/ECS provisioning) — `DEPLOY.md` is the
  runbook, but no cloud account has been used yet
- Architecture diagram, demo video, text description, public repo + license (submission
  requirements, not yet started)
