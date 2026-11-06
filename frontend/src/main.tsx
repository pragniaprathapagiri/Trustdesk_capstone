import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const api = "/api";
type Ticket = {ticket_id:string; subject:string; body:string; created_at:string; status:string};
type ActionState = {action_id:string;status:string;idempotent?:boolean};

async function call(path:string, options?:RequestInit) {
  const response = await fetch(api + path, {headers:{Authorization:"Bearer trustdesk-demo","Content-Type":"application/json"}, ...options});
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [triage, setTriage] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [action, setAction] = useState<ActionState|null>(null);
  const [traces, setTraces] = useState<any[]>([]);
  const [evals, setEvals] = useState<any[]>([]);

  async function refreshTickets() { setTickets((await call("/tickets")).items); }
  useEffect(() => { refreshTickets(); call("/evaluations").then(setEvals).catch(() => {}); }, []);

  async function openTicket(id:string) {
    const detail = await call(`/tickets/${id}`);
    setSelected(detail); setTriage(null); setDraft(null); setAction(null);
    setTraces(await call(`/traces?ticket_id=${id}`));
  }
  async function runTriage() {
    const result = await call(`/tickets/${selected.ticket.ticket_id}/triage`, {method:"POST"});
    setTriage(result); setTraces(await call(`/traces?ticket_id=${selected.ticket.ticket_id}`));
  }
  async function runDraft() {
    const result = await call(`/tickets/${selected.ticket.ticket_id}/draft`, {method:"POST"});
    setDraft(result); setTraces(await call(`/traces?ticket_id=${selected.ticket.ticket_id}`));
  }
  async function requestAction() {
    const tool = draft.recommended_actions.find((a:string) => a === "start_refund_review" || a === "create_replacement_order");
    if (!tool) return;
    const result = await call("/actions", {method:"POST", body:JSON.stringify({
      ticket_id:selected.ticket.ticket_id, tool_name:tool,
      payload:{order_id:selected.ticket.order_id,idempotency_key:`${selected.ticket.ticket_id}-${tool}-1`,reason:"Policy-supported support review"}
    })});
    setAction(result);
  }
  async function decide(decision:string) {
    if (!action) return;
    const result = await call(`/actions/${action.action_id}/approval`, {method:"POST", body:JSON.stringify({reviewer_id:"demo-manager",decision,reason:"Reviewed in dashboard"})});
    setAction({...action,...result});
  }
  async function executeAction() {
    if (!action) return;
    const result = await call(`/actions/${action.action_id}/execute`, {method:"POST"});
    setAction({...action,...result});
  }
  async function runEval() { const result = await call("/evaluations/run",{method:"POST"}); setEvals([result,...evals]); }

  return <div className="app">
    <aside><div className="brand">Trust<span>Desk</span></div><nav><b>Operations</b><button className="active">Support inbox</button><button onClick={runEval}>Evaluations</button></nav><div className="profile">Demo Agent<br/><small>support_manager</small></div></aside>
    <main>
      <header><div><h1>Support inbox</h1><p>AI-assisted operations with human approval</p></div><button className="primary" onClick={runEval}>Run evaluation</button></header>
      <div className="layout">
        <section className="ticket-list"><h2>Tickets</h2>{tickets.map(t => <button key={t.ticket_id} className={selected?.ticket.ticket_id===t.ticket_id?"ticket selected":"ticket"} onClick={()=>openTicket(t.ticket_id)}><strong>{t.subject}</strong><span>{t.ticket_id}</span><small>{t.body.slice(0,70)}...</small></button>)}</section>
        <section className="detail">
          {!selected ? <div className="empty">Select a ticket to begin</div> : <>
            <div className="detail-head"><div><span>CASE {selected.ticket.ticket_id}</span><h2>{selected.ticket.subject}</h2></div><button className="primary" onClick={runTriage}>Run AI triage</button></div>
            <article className="customer-message">{selected.ticket.body}</article>
            {selected.customer && <div className="context"><div><small>CUSTOMER</small><b>{selected.customer.name}</b><span>{selected.customer.email}</span></div>{selected.order && <div><small>ORDER</small><b>{selected.order.order_id}</b><span>{selected.order.status} · {selected.order.total} {selected.order.currency}</span></div>}</div>}
            {triage && <div className="cards"><div><small>Category</small><b>{triage.category}</b></div><div><small>Priority</small><b className={`priority ${triage.priority}`}>{triage.priority}</b></div><div><small>Escalation</small><b>{triage.should_escalate ? "Required" : "Not needed"}</b></div></div>}
            <div className="actions"><button className="secondary" onClick={runDraft}>Generate cited draft</button>{draft?.recommended_actions?.some((a:string)=>["start_refund_review","create_replacement_order"].includes(a)) && <button className="secondary" onClick={requestAction}>Request approval action</button>}</div>
            {draft && <article className="draft"><div className="section-title">AI draft <span className="badge">{draft.status}</span></div><p>{draft.body}</p><small>Citations</small><div>{draft.citations.map((id:string)=><span className="chip" key={id}>{id}</span>)}</div>{draft.recommended_actions.length>0 && <><small>Suggested actions</small><div>{draft.recommended_actions.map((a:string)=><span className="chip" key={a}>{a}</span>)}</div></>}</article>}
            {action && <article className="approval"><div className="section-title">Human approval</div><div className={`status ${action.status}`}>{action.status.replace("_"," ").toUpperCase()} {action.idempotent?"· already created":""}</div><div className="approval-buttons">{action.status==="approval_required" && <><button className="approve" onClick={()=>decide("approved")}>Approve & execute</button><button className="reject" onClick={()=>decide("rejected")}>Reject</button></>}{action.status==="approved" && <button className="approve" onClick={executeAction}>Execute approved action</button>}</div></article>}
            {traces.length>0 && <details className="trace"><summary>Audit traces ({traces.length})</summary>{traces.map(t=><pre key={t.run_id}>{JSON.stringify(t,null,2)}</pre>)}</details>}
          </>}
        </section>
        <section className="eval-panel"><h2>Evaluation</h2>{evals[0] ? <><div className="metric"><span>Triage accuracy</span><b>{Math.round(evals[0].triage_accuracy*100)}%</b></div><div className="metric"><span>Citation coverage</span><b>{Math.round(evals[0].citation_coverage*100)}%</b></div><div className="metric"><span>Unsafe blocked</span><b>{Math.round(evals[0].unsafe_action_block_rate*100)}%</b></div><div className="metric"><span>Escalation accuracy</span><b>{Math.round(evals[0].escalation_accuracy*100)}%</b></div></>:<p>Run the evaluation suite to see metrics.</p>}</section>
      </div>
    </main>
  </div>;
}
createRoot(document.getElementById("root")!).render(<App />);
