import json
from pathlib import Path
from sqlalchemy.orm import Session
from .models import EvalRun
from .services import triage, draft, run_id


def run_evaluation(db: Session, data_dir: Path) -> dict:
    cases = [json.loads(line) for line in (data_dir / "eval_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    results, triage_hits, priority_hits, citation_hits, unsafe_hits, escalation_hits = [], 0, 0, 0, 0, 0
    for case in cases:
        expected = case["expected"]
        predicted = triage(db, case["ticket_id"])
        generated = draft(db, case["ticket_id"])
        category_ok = predicted["category"] == expected["category"]
        priority_ok = predicted["priority"] == expected["priority"]
        citation_ok = set(expected.get("must_cite_doc_ids", [])).issubset(set(generated["citations"]))
        actions = set(generated["recommended_actions"])
        disallowed = set(expected.get("disallowed_actions", []))
        unsafe_ok = not actions.intersection(disallowed)
        escalation_ok = predicted["should_escalate"] == expected["should_escalate"]
        triage_hits += category_ok; priority_hits += priority_ok; citation_hits += citation_ok
        unsafe_hits += unsafe_ok; escalation_hits += escalation_ok
        passed = category_ok and priority_ok and citation_ok and unsafe_ok and escalation_ok
        results.append({"case_id": case["case_id"], "passed": passed, "predicted_category": predicted["category"],
                        "predicted_priority": predicted["priority"], "citations": generated["citations"],
                        "recommended_actions": sorted(actions), "should_escalate": predicted["should_escalate"]})
    total = len(cases)
    metrics = {
        "total_cases": total,
        "category_accuracy": round(triage_hits / total, 4),
        "priority_accuracy": round(priority_hits / total, 4),
        "triage_accuracy": round((triage_hits + priority_hits) / (2 * total), 4),
        "citation_coverage": round(citation_hits / total, 4),
        "unsafe_action_block_rate": round(unsafe_hits / total, 4),
        "escalation_accuracy": round(escalation_hits / total, 4),
    }
    obj = EvalRun(eval_run_id=run_id("eval"), metrics=metrics, case_results=results)
    db.add(obj); db.commit()
    return {"eval_run_id": obj.eval_run_id, **metrics, "case_results": results}
