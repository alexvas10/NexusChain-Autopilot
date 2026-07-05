import datetime

from pydantic import BaseModel


class IntakeRequest(BaseModel):
    workflow: str  # "rfq" | "disruption"
    text: str


class IntakeResponse(BaseModel):
    decision: str
    reasoning: str
    exception_id: int
    quote: dict | None = None


class ExceptionOut(BaseModel):
    id: int
    workflow: str
    summary: str
    payload: str
    decision: str
    reasoning: str
    status: str
    details: str | None
    action_log: str | None
    payload_archive_uri: str | None
    resolution_notes: str | None
    created_at: datetime.datetime
    resolved_at: datetime.datetime | None

    class Config:
        from_attributes = True


class DecisionRequest(BaseModel):
    action: str  # "approve" | "reject"
    notes: str | None = None


class DisruptionAlertRequest(BaseModel):
    shipment_id: str
    alert_text: str
    location: str | None = None


class DisruptionAlertResponse(BaseModel):
    decision: str
    exception_id: int
    cost_delta: float | None = None
    recommended_route: dict | None = None
    action_log: str | None = None
