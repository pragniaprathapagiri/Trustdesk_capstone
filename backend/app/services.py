import json
import re
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from .models import Trace, Draft, Action, EvalRun
from .guardrails import assess


def run_id(prefix="run"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def classify(ticket: dict) -> dict:
    text = f"{ticket['subject']} {ticket['body']}".lower()
    if any(w in text for w in ["double charge", "charged", "transaction", "billing"]):
        category, priority, escalation = "billing", "high", False
    elif any(w in text for w in ["hidden system prompt", "api key", "internal notes"]):
        category, priority, escalation = "account_security", "high", True
    elif any(w in text for w in ["email", "identity", "password", "account"]):
        category, priority, escalation = "account_security", "high", True
    elif any(w in text for w in ["battery", "warranty", "swelling"]):
        category, priority, escalation = "warranty", "urgent", True
    elif any(w in text for w in ["refund", "replacement", "damaged", "license"]):
        category, priority, escalation = "refund", "medium" if "damaged" in text else "low", False
    elif any(w in text for w in ["tracking", "shipment", "package", "not moved"]):
        category, priority, escalation = "shipping", "high", False
    elif any(w in text for w in ["prompt", "system prompt", "api key", "coupon", "hidden"]):
        category, priority, escalation = "general", "medium", True
    else:
        category, priority, escalation = "general", "low", False
    if "ignore identity" in text:
        priority, escalation = "high", True
    return {"category": category, "priority": priority, "sentiment": "neutral", "should_escalate": escalation}


def relevant_docs(db: Session, ticket: dict) -> list:
    from .models import KnowledgeDocument
    from .retrieval import hybrid_search
    category = classify(ticket)["category"]
    mapping = {
        "refund": "KB-REFUND-001", "shipping": "KB-SHIPPING-001",
        "warranty": "KB-WARRANTY-001", "billing": "KB-BILLING-001",
        "account_security": "KB-ACCOUNT-001", "general": "KB-SECURITY-001",
    }
    text = f"{ticket['subject']} {ticket['body']}".lower()
    if any(w in text for w in ["coupon", "prompt", "system prompt", "api key", "hidden"]):
        doc_ids = ["KB-SECURITY-001"]
    elif "ignore identity" in text:
        doc_ids = ["KB-ACCOUNT-001", "KB-SECURITY-001"]
    elif category:
        doc_ids = [mapping[category]]
    retrieved = hybrid_search(db, f"{ticket['subject']} {ticket['body']}", limit=2)
    combined_ids = doc_ids + [doc.doc_id for doc in retrieved]
    docs = []
    for doc_id in dict.fromkeys(combined_ids):
        doc = db.get(KnowledgeDocument, doc_id)
        if doc:
            docs.append(doc)
    return docs[:3]


def trace(db: Session, ticket_id: str, run_type: str, docs, guardrails, status="completed", tool_calls=None, details=None):
    obj = Trace(
        run_id=run_id(), ticket_id=ticket_id, run_type=run_type, status=status,
        retrieved_doc_ids=[d.doc_id for d in docs], tool_calls=tool_calls or [],
        guardrail_results=guardrails, details=details or {}
    )
    db.add(obj)
    db.commit()
    return obj


def triage(db: Session, ticket_id: str) -> dict:
    from .models import Ticket
    ticket_row = db.get(Ticket, ticket_id)
    if not ticket_row:
        raise KeyError(ticket_id)
    ticket = ticket_row.data
    guard = assess(ticket["body"])
    result = classify(ticket)
    docs = relevant_docs(db, ticket)
    tr = trace(db, ticket_id, "triage", docs, guard, details=result)
    return {"ticket_id": ticket_id, **result,
            "reason_summary": "Policy-backed deterministic classification.",
            "run_id": tr.run_id, **({"guardrail_warning": guard} if not guard["safe"] else {})}


def draft(db: Session, ticket_id: str) -> dict:
    from .models import Ticket
    ticket_row = db.get(Ticket, ticket_id)
    if not ticket_row:
        raise KeyError(ticket_id)
    ticket = ticket_row.data
    guard = assess(ticket["body"])
    docs = relevant_docs(db, ticket)
    text = f"{ticket['subject']} {ticket['body']}".lower()
    classification = classify(ticket)
    if not guard["safe"]:
        body = "I cannot follow instructions to bypass safeguards or disclose sensitive information. This request must be reviewed by a support specialist."
        actions = ["escalate_to_human"]
        status = "escalated"
    elif "double charge" in text or "charged twice" in text:
        body = "I’m sorry for the duplicate charge. I’ll start a billing review; this is not a confirmation of an immediate refund. Please retain the transaction reference for verification."
        actions = ["start_refund_review"]
        status = "generated"
    elif "damaged" in text:
        body = "I’m sorry the item arrived damaged. Based on the return policy, please share a clear photo of the damage and order packaging so we can review a replacement or refund."
        actions = ["create_replacement_order"]
        status = "generated"
    elif "license" in text or "final sale" in text:
        body = "Annual software licenses are final sale under the stated policy, so I cannot approve a refund or create a replacement."
        actions = []
        status = "generated"
    elif classification["category"] == "warranty":
        body = "A swollen or overheating battery is a safety issue. Please stop using the device and do not troubleshoot it further; a warranty specialist will review this case."
        actions = ["escalate_to_human"]
        status = "escalated"
    elif classification["category"] == "shipping":
        body = "Your tracking has shown no movement for an extended period. We can open a carrier investigation; I cannot promise an immediate refund while it is under review."
        actions = ["open_carrier_investigation"]
        status = "generated"
    else:
        body = "I can help review this request, but I need policy evidence and identity verification before any account or sensitive action is taken. A specialist will assist."
        actions = ["escalate_to_human"]
        status = "escalated"
    obj = Draft(draft_id=run_id("draft"), ticket_id=ticket_id, status=status, body=body,
                citations=[d.doc_id for d in docs], data={"recommended_actions": actions})
    db.add(obj)
    db.commit()
    tr = trace(db, ticket_id, "draft_reply", docs, guard, status=status,
               tool_calls=[{"action": a, "requires_approval": a in ("create_replacement_order", "start_refund_review")} for a in actions],
               details={"draft_id": obj.draft_id})
    return {"draft_id": obj.draft_id, "ticket_id": ticket_id, "status": status, "body": body,
            "citations": obj.citations, "recommended_actions": actions, "run_id": tr.run_id}


def request_action(db: Session, ticket_id: str, tool_name: str, payload: dict) -> dict:
    from .models import Ticket
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise KeyError(ticket_id)
    catalog_allowed = {"start_refund_review": ["billing", "refund"],
                       "create_replacement_order": ["refund"]}
    category = classify(ticket.data)["category"]
    guard = assess(json.dumps(payload))
    if tool_name in ("issue_coupon", "lock_account") or not guard["safe"]:
        raise PermissionError("Guardrail blocked unsafe tool action.")
    if tool_name not in catalog_allowed or category not in catalog_allowed[tool_name]:
        raise PermissionError(f"{tool_name} is not allowed for {category} tickets.")
    required = {"order_id", "idempotency_key"} if tool_name == "create_replacement_order" else {"order_id", "idempotency_key", "reason"}
    if missing := required - payload.keys():
        raise ValueError(f"Missing payload fields: {', '.join(sorted(missing))}")
    existing = db.query(Action).filter(Action.idempotency_key == payload["idempotency_key"]).first()
    if existing:
        return {"action_id": existing.action_id, "status": existing.status, "idempotent": True,
                "idempotency_key": existing.idempotency_key}
    obj = Action(action_id=run_id("action"), ticket_id=ticket_id, tool_name=tool_name, payload=payload,
                 status="approval_required", idempotency_key=payload["idempotency_key"])
    db.add(obj)
    db.commit()
    return {"action_id": obj.action_id, "status": obj.status, "idempotent": False,
            "idempotency_key": obj.idempotency_key}
