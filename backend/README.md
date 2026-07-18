# NexusChain Autopilot — backend

FastAPI backend for the Track 4 "NexusChain Autopilot" agent: a shared agent core (Qwen
tool-use agent + exception classifier, exception queue via SQLAlchemy, audit trail)
with two pluggable workflow playbooks:

- **Workflow A — RFQ intake** (`app/workflows/rfq.py`): parses a free-text quote request
  into line items via Qwen, prices each against mock inventory/vendor-catalog tools
  (`app/tools.py`, fixtures in `app/mock_data.py`), and routes anything with a missing or
  unmatched spec to human review. On rejection, Qwen drafts the clarification email back
  to the customer from the unresolved items and the reviewer's note.
- **Workflow B — disruption response** (`app/workflows/disruption.py`): a Qwen
  **function-calling agent** (`app/agent.py`) investigates each shipment alert itself —
  choosing which tools to call (ERP orders, routes, weather) and in what order — and
  recommends whether to reroute, with every tool call captured in an auditable trace.
  A deterministic layer then recomputes the cost delta from source data and forces human
  approval above a configurable threshold (`DISRUPTION_COST_APPROVAL_THRESHOLD`, default
  $200) or whenever the agent itself flags risk. Approval triggers `execute_reroute`
  (mock manifest update + customer notice); a Slack Incoming Webhook is used if
  `SLACK_WEBHOOK_URL` is set, otherwise messages are logged locally
  (`app/slack_client.py`).

Both endpoints archive the raw inbound payload to Alibaba Cloud OSS
(`app/oss_client.py`), falling back to a local directory when OSS isn't configured.

## Reliability model

All model access goes through `app/qwen_client.py`, which sets an explicit timeout and
one retry, and every call site is fail-safe: if Qwen is unreachable or returns something
unparseable, classification degrades to `human_review` (with the error captured in the
reasoning), extraction degrades to "no items → human review", and reply drafting is
skipped with a note in the action log. A model outage can therefore never auto-approve
anything or crash a request.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set DASHSCOPE_API_KEY
```

## Run locally

```bash
uvicorn app.main:app --reload
```

- `GET /health` — liveness check
- `POST /intake` — `{"workflow": "rfq", "text": "..."}` → RFQ intake only; parses, prices,
  and either auto-approves (`quote` in the response) or files a pending exception
- `POST /webhooks/disruption` — `{"shipment_id": "...", "alert_text": "...", "location": "..."}`
  → runs the tool-use agent; returns the recommended route, cost delta, and the agent's
  tool-call trace (`agent_trace`), and either auto-executes the reroute or files a pending
  exception (and posts to Slack if configured)
- `GET /exceptions` — list exceptions (JSON), optional `?status=pending`
- `POST /exceptions/{id}/decision` — `{"action": "approve"|"reject", "notes": "..."}` →
  also runs the workflow's post-decision action (finalize quote / execute reroute /
  draft the customer clarification email)
- `GET /dashboard` — HTML page to review/approve/reject pending exceptions, with
  workflow-specific detail (priced line items, or affected orders + route cost delta +
  the agent's tool-call trace)

## Try it end-to-end

```bash
curl -X POST localhost:8000/intake \
  -H "Content-Type: application/json" \
  -d '{"workflow": "rfq", "text": "I need 50 heavy-duty bolts, ship ASAP"}'

curl -X POST localhost:8000/webhooks/disruption \
  -H "Content-Type: application/json" \
  -d '{"shipment_id": "SHIP-7781", "alert_text": "Severe winter storm hitting the Chicago port", "location": "Chicago, IL"}'
```

The RFQ call comes back `decision: "human_review"` (missing bolt size/spec) with an
`exception_id`; the disruption call returns `cost_delta: 1200.0`, the agent's
`agent_trace`, and `decision: "human_review"` (exceeds the cost threshold). Open
`http://localhost:8000/dashboard` to see both and approve/reject them. Both paths have
been verified live against the real Qwen (DashScope) API.

## Tests

```bash
pytest
```

25 tests, no network or API key needed — all Qwen calls are stubbed at their usage
sites. Coverage: RFQ pricing math and review flags, disruption cost-delta computation
and the threshold/agent guardrail interplay, the agent loop protocol (scripted model,
real tool implementations, error paths, turn budget), and the full HTTP API including
approve/reject side effects and dashboard rendering.

## Deploying

See `DEPLOY.md` for the Alibaba Cloud runbook (RDS/PolarDB, OSS bucket, ACR + ECS). A
`Dockerfile` is included and has been verified locally (builds, boots, serves `/health`
and `/dashboard`); the Postgres path has also been verified end-to-end against a real
local Postgres container via the `psycopg3` driver (`postgresql+psycopg://...` — note the
driver prefix, plain `postgresql://` will fail since psycopg2 isn't installed).
