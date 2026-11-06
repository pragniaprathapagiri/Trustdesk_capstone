from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import get_db, Base, engine
from .models import Customer, Order, Ticket, KnowledgeDocument, Action, Approval
from .seed import seed
from .services import triage, draft, request_action
from .evaluation import run_evaluation
from .config import settings

app = FastAPI(title="TrustDesk API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    seed()


def authorize(authorization: str | None = Header(None)):
    if authorization and authorization.removeprefix("Bearer ") == settings.demo_token:
        return
    # Demo mode remains usable in Docker and local Swagger when no token is supplied.


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"status": "healthy", "provider": settings.llm_provider}


@app.get("/api/tickets")
def tickets(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.query(Ticket).offset((page - 1) * limit).limit(limit).all()
    return {"items": [r.data for r in rows], "total": db.query(Ticket).count(), "page": page, "limit": limit}


@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id: str, db: Session = Depends(get_db)):
    row = db.get(Ticket, ticket_id)
    if not row: raise HTTPException(404, "Ticket not found")
    customer = db.get(Customer, row.customer_id)
    order = db.get(Order, row.order_id) if row.order_id else None
    return {"ticket": row.data, "customer": customer.data if customer else None, "order": order.data if order else None}


@app.post("/api/tickets/{ticket_id}/triage")
def run_triage(ticket_id: str, db: Session = Depends(get_db)):
    try: return triage(db, ticket_id)
    except KeyError: raise HTTPException(404, "Ticket not found")


@app.post("/api/tickets/{ticket_id}/draft")
def run_draft(ticket_id: str, db: Session = Depends(get_db)):
    try: return draft(db, ticket_id)
    except KeyError: raise HTTPException(404, "Ticket not found")


@app.post("/api/knowledge/search")
def search_knowledge(query: str, limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    tokens = set(query.lower().split())
    rows = db.query(KnowledgeDocument).all()
    results = []
    for row in rows:
        score = len(tokens.intersection(set(row.content.lower().split())))
        results.append({"doc_id": row.doc_id, "title": row.title, "snippet": row.content[:280], "score": score})
    return {"query": query, "results": sorted(results, key=lambda x: x["score"], reverse=True)[:limit]}


@app.post("/api/knowledge/ingest")
def ingest(documents: dict, db: Session = Depends(get_db)):
    ingested = []
    for doc in documents.get("documents", []):
        obj = KnowledgeDocument(doc_id=doc["doc_id"], title=doc["title"], content=doc["content"],
                                source_path=doc.get("source_path", ""), data={k: v for k, v in doc.items() if k not in ("doc_id", "title", "content", "source_path")})
        db.merge(obj); ingested.append(doc["doc_id"])
    db.commit()
    return {"ingested": len(ingested), "document_ids": ingested}


@app.post("/api/actions")
def create_action(payload: dict, db: Session = Depends(get_db)):
    try:
        return request_action(db, payload["ticket_id"], payload["tool_name"], payload["payload"])
    except KeyError as exc: raise HTTPException(404, "Ticket not found")
    except PermissionError as exc: raise HTTPException(403, str(exc))
    except ValueError as exc: raise HTTPException(422, str(exc))


@app.post("/api/actions/{action_id}/approval")
def approve_action(action_id: str, decision: dict, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if not action: raise HTTPException(404, "Action not found")
    reviewer = decision.get("reviewer_id", "support-manager")
    chosen = decision.get("decision")
    if chosen not in ("approved", "rejected"): raise HTTPException(422, "Decision must be approved or rejected")
    obj = Approval(approval_id="approval_" + action_id, action_id=action_id, reviewer_id=reviewer,
                   decision=chosen, reason=decision.get("reason", ""))
    db.merge(obj)
    action.status = "approved" if chosen == "approved" else "rejected"
    db.commit()
    return {"action_id": action_id, "status": action.status}


@app.post("/api/actions/{action_id}/execute")
def execute_action(action_id: str, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if not action: raise HTTPException(404, "Action not found")
    if action.status != "approved":
        raise HTTPException(409, "Execution requires an approved action")
    if action.result:
        return {"action_id": action_id, "status": "executed", "idempotent": True, "result": action.result}
    action.result = {"mock_operation": action.tool_name, "order_id": action.payload.get("order_id"),
                     "status": "submitted", "reference": "TD-" + action.action_id[-8:].upper()}
    action.status = "executed"
    db.commit()
    return {"action_id": action_id, "status": "executed", "idempotent": False, "result": action.result}


@app.get("/api/actions/{action_id}")
def get_action(action_id: str, db: Session = Depends(get_db)):
    action = db.get(Action, action_id)
    if not action: raise HTTPException(404, "Action not found")
    return {"action_id": action.action_id, "ticket_id": action.ticket_id, "tool_name": action.tool_name,
            "payload": action.payload, "status": action.status, "idempotency_key": action.idempotency_key,
            "result": action.result}


@app.get("/api/traces")
def traces(ticket_id: str | None = None, db: Session = Depends(get_db)):
    from .models import Trace
    query = db.query(Trace)
    if ticket_id: query = query.filter(Trace.ticket_id == ticket_id)
    rows = query.order_by(Trace.created_at.desc()).all()
    return [{"run_id": r.run_id, "ticket_id": r.ticket_id, "run_type": r.run_type, "status": r.status,
             "retrieved_doc_ids": r.retrieved_doc_ids, "tool_calls": r.tool_calls,
             "guardrail_result": r.guardrail_results, "details": r.details, "created_at": r.created_at.isoformat()} for r in rows]


@app.post("/api/evaluations/run")
def run_eval(db: Session = Depends(get_db)):
    return run_evaluation(db, settings.data_dir)


@app.get("/api/evaluations")
def evals(db: Session = Depends(get_db)):
    from .models import EvalRun
    return [{"eval_run_id": r.eval_run_id, "metrics": r.metrics, "case_results": r.case_results, "created_at": r.created_at.isoformat()}
            for r in db.query(EvalRun).order_by(EvalRun.created_at.desc()).all()]
