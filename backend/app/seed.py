import json
import re
from pathlib import Path
from sqlalchemy.orm import Session
from .database import engine, Base, SessionLocal
from .models import Customer, Order, Ticket, KnowledgeDocument
from .config import settings


def doc_metadata(filename: str) -> dict:
    mapping = {
        "refund_policy.md": ("KB-REFUND-001", "Refund and Return Policy"),
        "shipping_policy.md": ("KB-SHIPPING-001", "Shipping Policy"),
        "warranty_policy.md": ("KB-WARRANTY-001", "Warranty Policy"),
        "billing_policy.md": ("KB-BILLING-001", "Billing Policy"),
        "account_security_policy.md": ("KB-ACCOUNT-001", "Account Security Policy"),
        "support_security_playbook.md": ("KB-SECURITY-001", "Support Security Playbook"),
        "coupon_policy.md": ("KB-COUPON-001", "Coupon Policy"),
        "adversarial_vendor_note.md": ("KB-ADVERSARIAL-001", "Vendor Advisory Note"),
    }
    return mapping.get(filename, (f"KB-{filename.upper()[:20]}", filename.replace("_", " ").title()))


def seed(db: Session | None = None):
    Base.metadata.create_all(engine)
    owns = db is None
    db = db or SessionLocal()
    data_dir = Path(settings.data_dir)
    try:
        for filename, model, id_key in [
            ("customers.json", Customer, "customer_id"),
            ("orders.json", Order, "order_id"),
            ("tickets.json", Ticket, "ticket_id"),
        ]:
            records = json.loads((data_dir / filename).read_text(encoding="utf-8"))
            for record in records:
                rid = record[id_key]
                if db.get(model, rid):
                    continue
                values = {"data": record}
                if model is Customer:
                    values = {"customer_id": rid, "data": record}
                elif model is Order:
                    values = {"order_id": rid, "customer_id": record["customer_id"], "data": record}
                else:
                    values = {
                        "ticket_id": rid,
                        "customer_id": record["customer_id"],
                        "order_id": record.get("order_id"),
                        "subject": record["subject"],
                        "body": record["body"],
                        "status": record.get("status", "open"),
                        "data": record,
                    }
                db.add(model(**values))
        kb_dir = data_dir / "knowledge_base"
        if kb_dir.exists():
            for path in kb_dir.glob("*"):
                doc_id, title = doc_metadata(path.name)
                if db.get(KnowledgeDocument, doc_id):
                    continue
                db.add(KnowledgeDocument(
                    doc_id=doc_id, title=title, content=path.read_text(encoding="utf-8"),
                    source_path=str(path), data={"audience": "support", "version": 1}
                ))
        db.commit()
    finally:
        if owns:
            db.close()
