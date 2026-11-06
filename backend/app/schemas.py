from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Pagination(BaseModel):
    items: list[Any]
    total: int
    page: int
    limit: int


class Triage(BaseModel):
    ticket_id: str
    category: Literal["shipping", "refund", "warranty", "billing", "account_security", "general"]
    priority: Literal["low", "medium", "high", "urgent"]
    sentiment: str
    should_escalate: bool
    reason_summary: str
    run_id: str


class DraftRequest(BaseModel):
    ticket_id: str


class ApprovalRequest(BaseModel):
    reviewer_id: str = "support-manager"
    decision: Literal["approved", "rejected"]
    reason: str = ""


class ActionRequest(BaseModel):
    ticket_id: str
    tool_name: str = "start_refund_review"
    payload: dict[str, Any]


class IngestRequest(BaseModel):
    documents: list[dict[str, Any]]
