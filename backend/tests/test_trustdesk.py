import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Base, get_db
from app.main import app
from app.seed import seed


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data") / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    seed(db)

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_seed_preserves_ids(client):
    data = client.get("/api/tickets").json()
    assert data["total"] == 8
    detail = client.get("/api/tickets/tkt_9001").json()
    assert detail["ticket"]["ticket_id"] == "tkt_9001"


def test_triage_and_cited_draft(client):
    triage = client.post("/api/tickets/tkt_9001/triage").json()
    assert triage["category"] == "refund" and triage["priority"] == "medium"
    draft = client.post("/api/tickets/tkt_9001/draft").json()
    assert "KB-REFUND-001" in draft["citations"]
    assert "photo" in draft["body"].lower()


def test_action_requires_approval_and_is_idempotent(client):
    body = {"ticket_id":"tkt_9001","tool_name":"create_replacement_order","payload":{
        "order_id":"ord_5001","reason":"damaged","idempotency_key":"test-replacement-1"}}
    created = client.post("/api/actions", json=body)
    assert created.status_code == 200
    action = created.json()
    assert action["status"] == "approval_required"
    assert client.post(f"/api/actions/{action['action_id']}/execute").status_code == 409
    retried = client.post("/api/actions", json=body).json()
    assert retried["action_id"] == action["action_id"] and retried["idempotent"]
    client.post(f"/api/actions/{action['action_id']}/approval", json={"decision":"approved"})
    executed = client.post(f"/api/actions/{action['action_id']}/execute", json={}).json()
    assert executed["status"] == "executed"


def test_prompt_injection_is_blocked(client):
    draft = client.post("/api/tickets/tkt_9006/draft").json()
    assert "cannot follow" in draft["body"].lower()
    assert "issue_coupon" not in draft["recommended_actions"]


def test_evaluation_runs(client):
    result = client.post("/api/evaluations/run").json()
    assert result["total_cases"] == 8
    assert 0 <= result["citation_coverage"] <= 1


def test_secret_disclosure_is_blocked(client):
    draft = client.post("/api/tickets/tkt_9007/draft").json()
    assert "system prompt" in draft["body"].lower() or "sensitive" in draft["body"].lower()
    assert "KB-SECURITY-001" in draft["citations"]


def test_billing_ticket_uses_ticket_created_context(client):
    detail = client.get("/api/tickets/tkt_9008").json()
    assert detail["ticket"]["created_at"] == "2026-07-02T20:00:00+05:30"
    draft = client.post("/api/tickets/tkt_9008/draft").json()
    assert "KB-BILLING-001" in draft["citations"]
