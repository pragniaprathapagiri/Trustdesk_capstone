# TrustDesk 4:30 Demo Script

## 0:00-0:25 - Open and overview
Show Docker running, dashboard, and Swagger. Explain that TrustDesk preserves canonical seed IDs and uses human approval.

## 0:25-0:55 - Open damaged-earbuds ticket
Select `tkt_9001`. Highlight customer, linked order, original message, and 2026-06-28 ticket-relative context.

## 0:55-1:20 - Triage
Click Run AI triage. Narrate refund, medium priority, and policy context.

## 1:20-1:55 - Draft and citations
Generate draft. Point out the photo request and `KB-REFUND-001`.

## 1:55-2:35 - Approval-gated action
Request replacement review. Explain that the backend created `approval_required`, then approve and execute. Retry the request to demonstrate the idempotency key.

## 2:35-3:05 - Adversarial case
Open `tkt_9006`. Trigger draft or inspect `eval_006`. Show injection refusal and no coupon recommendation.

## 3:05-3:35 - Audit traces and secret disclosure
Show trace viewer, retrieved document IDs, guardrail result, and status. Mention API keys/prompts remain undisclosed.

## 3:35-4:15 - Evaluation
Run evaluation and explain total cases, citations, unsafe blocking, and escalation metrics.

## 4:15-4:30 - Close
Summarize approval boundary, auditability, and documented local/demo limitations.

## Recording checklist
- [ ] Docker services healthy
- [ ] Port 3000 dashboard loads
- [ ] Ticket list has 8 records
- [ ] Tickets `9001` and `9006` load
- [ ] Triage and draft buttons work
- [ ] Approval state reaches executed
- [ ] Repeated action remains single
- [ ] Evaluation endpoint returns JSON
- [ ] Swagger loads
