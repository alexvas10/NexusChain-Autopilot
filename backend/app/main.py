import datetime
import json
import uuid

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Exception_
from app.oss_client import store_payload
from app.schemas import (
    DecisionRequest,
    DisruptionAlertRequest,
    DisruptionAlertResponse,
    ExceptionOut,
    IntakeRequest,
    IntakeResponse,
)
from app.slack_client import send_approval_message
from app.workflows.disruption import execute_reroute, process_disruption
from app.workflows.rfq import process_rfq

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ops Autopilot")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fromjson"] = json.loads


def _execute_post_decision(record: Exception_) -> str:
    details = json.loads(record.details) if record.details else {}
    if record.workflow == "disruption":
        if record.status == "approved":
            route = details.get("recommended_route")
            if route:
                return execute_reroute(details.get("shipment_id"), route["id"])
            return "No reroute available to execute."
        return "Reroute rejected; shipment remains on original route."
    if record.workflow == "rfq":
        if record.status == "approved":
            return "Quote finalized and sent to customer."
        return "RFQ declined; no quote sent to customer."
    return record.action_log or ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/intake", response_model=IntakeResponse)
def intake(req: IntakeRequest, db: Session = Depends(get_db)):
    if req.workflow != "rfq":
        raise HTTPException(
            status_code=400,
            detail="workflow must be 'rfq' for /intake; use /webhooks/disruption for disruption alerts",
        )

    result = process_rfq(req.text)
    classification = result["classification"]
    needs_human = result["needs_human_review"]

    archive_uri = store_payload(f"rfq/{uuid.uuid4()}.txt", req.text)

    record = Exception_(
        workflow="rfq",
        summary=classification.get("summary", req.text[:200]),
        payload=req.text,
        decision=classification.get("decision", "human_review"),
        reasoning=classification.get("reasoning", ""),
        status="pending" if needs_human else "approved",
        payload_archive_uri=archive_uri,
        details=json.dumps(
            {
                "line_items": result["line_items"],
                "unresolved_items": result["unresolved_items"],
                "subtotal": result["subtotal"],
            }
        ),
    )
    if not needs_human:
        record.action_log = "Quote finalized and sent to customer."
        record.resolved_at = datetime.datetime.utcnow()

    db.add(record)
    db.commit()
    db.refresh(record)

    return IntakeResponse(
        decision=record.decision,
        reasoning=record.reasoning,
        exception_id=record.id,
        quote={
            "line_items": result["line_items"],
            "unresolved_items": result["unresolved_items"],
            "subtotal": result["subtotal"],
        },
    )


@app.post("/webhooks/disruption", response_model=DisruptionAlertResponse)
def disruption_webhook(req: DisruptionAlertRequest, db: Session = Depends(get_db)):
    result = process_disruption(req.shipment_id, req.alert_text, req.location)
    classification = result["classification"]
    needs_human = result.get("needs_human_review", True)

    archive_uri = store_payload(f"disruption/{uuid.uuid4()}.txt", req.alert_text)

    record = Exception_(
        workflow="disruption",
        summary=classification.get("summary", req.alert_text[:200]),
        payload=req.alert_text,
        decision=classification.get("decision", "human_review"),
        reasoning=classification.get("reasoning", ""),
        status="pending" if needs_human else "approved",
        payload_archive_uri=archive_uri,
        details=json.dumps({k: v for k, v in result.items() if k != "classification"}),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    if needs_human:
        send_approval_message(record.id, record.summary, result.get("cost_delta", 0.0))
    else:
        record.action_log = _execute_post_decision(record)
        record.resolved_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(record)

    return DisruptionAlertResponse(
        decision=record.decision,
        exception_id=record.id,
        cost_delta=result.get("cost_delta"),
        recommended_route=result.get("recommended_route"),
        action_log=record.action_log,
    )


@app.get("/exceptions", response_model=list[ExceptionOut])
def list_exceptions(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Exception_)
    if status:
        query = query.filter(Exception_.status == status)
    return query.order_by(Exception_.created_at.desc()).all()


@app.post("/exceptions/{exception_id}/decision", response_model=ExceptionOut)
def decide_exception(exception_id: int, req: DecisionRequest, db: Session = Depends(get_db)):
    record = db.get(Exception_, exception_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Exception not found")
    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    record.status = "approved" if req.action == "approve" else "rejected"
    record.resolution_notes = req.notes
    record.resolved_at = datetime.datetime.utcnow()
    record.action_log = _execute_post_decision(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    pending = (
        db.query(Exception_)
        .filter(Exception_.status == "pending")
        .order_by(Exception_.created_at.desc())
        .all()
    )
    resolved = (
        db.query(Exception_)
        .filter(Exception_.status != "pending")
        .order_by(Exception_.resolved_at.desc())
        .limit(20)
        .all()
    )
    return templates.TemplateResponse(
        request, "dashboard.html", {"pending": pending, "resolved": resolved}
    )


@app.post("/dashboard/{exception_id}/decision")
def dashboard_decide(
    exception_id: int,
    action: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    decide_exception(exception_id, DecisionRequest(action=action, notes=notes), db)
    return RedirectResponse(url="/dashboard", status_code=303)
