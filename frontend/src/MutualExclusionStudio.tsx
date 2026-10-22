import { useMemo, useState } from "react";
import { Activity, ArrowDownRight, CheckCircle2, CircleAlert, Clock3, Download, Play, RotateCcw, ShieldCheck, SkipForward } from "lucide-react";
import "./mutual-exclusion-studio.css";

const API = (import.meta as ImportMeta & { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL || "/api-proxy";
type TraceEvent = { step: number; event: string; [key: string]: unknown };
type Run = { id: number; lab_id: string; scenario: string; parameters: Record<string, unknown>; trace: TraceEvent[]; result: Record<string, unknown>; status: string; current_step: number; created_at: string };
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init });
  if (!response.ok) throw new Error((await response.text()).slice(0, 240) || `HTTP ${response.status}`);
  return response.json();
}
const scenarios = [
  { id: "simultaneous-requests", label: "Competing resource claims", description: "Three coordinators request one capacity-one recovery slot. The protocol orders requests and prevents overlapping ownership." },
  { id: "tie-break", label: "Equal timestamps & deterministic tie-break", description: "Requests with equal logical timestamps are ordered by process identifier, so all peers reach the same decision." },
  { id: "deferred-reply", label: "Deferred permission", description: "A process already competing for the critical section defers a reply; the waiting process cannot enter until permission is delivered." },
  { id: "delayed-delivery", label: "Delayed message delivery", description: "Inspect how a delayed permission message affects progress without changing the mutual-exclusion safety rule." },
];
const processInfo = [
  { id: "P1", name: "Incident coordinator", role: "Incident command · INC-1042" },
  { id: "P2", name: "Recovery controller", role: "Field response · UNIT-7" },
  { id: "P3", name: "Resource allocator", role: "Capacity reservation service" },
];
function pretty(value: unknown) { return typeof value === "string" ? value.replaceAll(".", " · ").replaceAll("-", " ") : JSON.stringify(value); }
export function MutualExclusionStudio() {
  const [scenario, setScenario] = useState(scenarios[0].id);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedStep, setSelectedStep] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const current = scenarios.find(s => s.id === scenario) || scenarios[0];
  const executed = run?.trace.slice(0, run.current_step) || [];
  const event = selectedStep === null ? executed.at(-1) : executed.find(e => e.step === selectedStep);
  const owner = useMemo(() => {
    let value: unknown = null;
    for (const item of executed) {
      if (item.event === "critical-section.enter") value = item.process ?? item.node ?? item.requester ?? "Process";
      if (item.event === "critical-section.exit") value = null;
      if (item.event === "resource.owner.changed") value = item.owner ?? null;
    }
    return value;
  }, [executed]);
  const result = run?.result || {};
  const checks = Object.entries(result).filter(([key, value]) => /invariant|maximum_concurrent|all_required|all_processes|application_updates/i.test(key) && (typeof value === "boolean" || typeof value === "number" || typeof value === "string"));
  async function createRun() {
    setBusy(true); setError(""); setNotice(""); setSelectedStep(null);
    try {
      const response = await api<{ run: Run }>("/experiments", { method: "POST", body: JSON.stringify({ lab_id: "mutex", scenario, parameters: { scenario, resource_id: "R-01", resource_name: "Recovery Slot R-01", incident_id: "INC-1042", capacity: 1 } }) });
      setRun(response.run); setNotice("Experiment persisted. Advance the event ledger to observe protocol decisions.");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to create experiment"); }
    finally { setBusy(false); }
  }
  async function step() {
    if (!run || run.current_step >= run.trace.length) return;
    setBusy(true); setError("");
    try {
      const response = await api<{ run: Run }>(`/experiments/${run.id}/step`, { method: "POST" });
      setRun(response.run); setSelectedStep(response.run.current_step);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to advance experiment"); }
    finally { setBusy(false); }
  }
  async function runAll() {
    if (!run) return;
    setBusy(true); setError("");
    try {
      let latest = run;
      while (latest.current_step < latest.trace.length) {
        const response = await api<{ run: Run }>(`/experiments/${latest.id}/step`, { method: "POST" });
        latest = response.run;
      }
      setRun(latest); setSelectedStep(latest.current_step); setNotice("Trace completed. Review the safety evidence and operation ledger.");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to complete experiment"); }
    finally { setBusy(false); }
  }
  async function reset() {
    if (!run) { setRun(null); return; }
    setBusy(true); setError("");
    try { const response = await api<{ run: Run }>(`/experiments/${run.id}/reset`, { method: "POST" }); setRun(response.run); setSelectedStep(null); setNotice("Execution cursor reset."); }
    catch (e) { setError(e instanceof Error ? e.message : "Reset endpoint unavailable; create a new run instead."); }
    finally { setBusy(false); }
  }
  function exportEvidence() {
    if (!run) return;
    const payload = { title: "AegisGrid Critical Resource Control Room", execution_mode: "deterministic simulation", resource: { id: "R-01", name: "Recovery Slot R-01", capacity: 1, linked_incident: "INC-1042" }, run, executed_trace: executed, exported_at: new Date().toISOString() };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `aegisgrid-mutex-run-${run.id}.json`; a.click(); URL.revokeObjectURL(url);
  }
  return <main className="mx-studio">
    <header className="mx-hero">
      <div><div className="mx-eyebrow"><ShieldCheck size={14}/> DISTRIBUTED SYSTEMS LAB / RESOURCE SAFETY</div><h1>Critical Resource Control Room</h1><p>Watch three independent coordinators negotiate access to one capacity-limited recovery resource. Every decision is tied to a backend-generated, persisted protocol trace.</p></div>
      <div className="mx-mode"><span className="mx-live-dot"/><div><b>SIMULATION MODE</b><small>No real dispatch resource is locked or changed</small></div></div>
    </header>
    <section className="mx-resource-banner">
      <div className="mx-resource-icon"><ShieldCheck size={25}/></div><div className="mx-resource-main"><span>PROTECTED RESOURCE · CAPACITY 1</span><h2>Recovery Slot R-01</h2><p>Linked teaching incident <b>INC-1042</b> · example operation: acknowledge incident, assign UNIT-7, reserve inventory</p></div>
      <div className="mx-owner"><span>CURRENT CRITICAL-SECTION OWNER</span><strong>{owner ? String(owner) : "NONE"}</strong><small>{owner ? "Exclusive access in this executed trace" : "Resource currently unowned"}</small></div>
    </section>
    <section className="mx-control-panel">
      <div className="mx-section-title"><div><span className="mx-kicker">01 / EXPERIMENT SETUP</span><h2>Choose the contention scenario</h2><p>Each scenario changes the backend-generated message schedule, not just the UI labels.</p></div><Activity size={20}/></div>
      <div className="mx-scenarios">{scenarios.map(s => <button key={s.id} className={scenario === s.id ? "mx-scenario selected" : "mx-scenario"} onClick={() => { setScenario(s.id); setRun(null); setNotice(""); }}><span>{s.id === "tie-break" ? "02" : s.id === "deferred-reply" ? "03" : s.id === "delayed-delivery" ? "04" : "01"}</span><b>{s.label}</b><small>{s.description}</small></button>)}</div>
      <div className="mx-toolbar"><div className="mx-run-state"><span className={run?.status === "completed" ? "mx-state-dot done" : "mx-state-dot"}/><div><b>{run ? `Run #${run.id} · ${run.status}` : "No experiment run yet"}</b><small>{run ? `Event ${run.current_step} of ${run.trace.length}` : "Create a persisted run to begin"}</small></div></div><div className="mx-actions"><button className="mx-btn primary" onClick={() => void createRun()} disabled={busy}><Play size={15}/> New run</button><button className="mx-btn" onClick={() => void step()} disabled={!run || busy || run.current_step >= run.trace.length}><SkipForward size={15}/> Next event</button><button className="mx-btn" onClick={() => void runAll()} disabled={!run || busy || run.current_step >= run.trace.length}><Play size={15}/> Run to completion</button><button className="mx-btn" onClick={() => void reset()} disabled={!run || busy}><RotateCcw size={15}/> Reset</button><button className="mx-btn" onClick={exportEvidence} disabled={!run}><Download size={15}/> Export JSON</button></div></div>
      {notice && <div className="mx-notice"><CheckCircle2 size={15}/>{notice}</div>}{error && <div className="mx-error"><CircleAlert size={15}/>{error}</div>}
    </section>
    <div className="mx-layout">
      <section className="mx-panel mx-topology"><div className="mx-section-title compact"><div><span className="mx-kicker">02 / PROCESS TOPOLOGY</span><h2>Who is competing?</h2></div><span className="mx-pill">3 peers · 1 resource</span></div>
        <div className="mx-network"><div className="mx-resource-node"><ShieldCheck size={21}/><b>R-01</b><small>Capacity = 1</small><span className={owner ? "occupied" : ""}>{owner ? "OWNED" : "AVAILABLE"}</span></div><div className="mx-process-list">{processInfo.map((p, i) => <div className="mx-process" key={p.id}><div className={owner && String(owner).includes(p.id) ? "mx-process-avatar active" : "mx-process-avatar"}>{p.id}</div><div><b>{p.name}</b><small>{p.role}</small><span>{executed.some(e => String(e.process || e.node || "").includes(p.id)) ? "Participating in trace" : "Awaiting protocol events"}</span></div><ArrowDownRight size={17}/></div>)}</div></div>
        <p className="mx-footnote">Arrows represent conceptual request/reply paths. The event ledger below is authoritative for message direction and ordering.</p>
      </section>
      <section className="mx-panel mx-evidence"><div className="mx-section-title compact"><div><span className="mx-kicker">03 / SAFETY EVIDENCE</span><h2>Protocol invariants</h2></div><ShieldCheck size={20}/></div>
        {!run && <div className="mx-empty">Create a run to populate evidence from the experiment result.</div>}
        {run && <><div className="mx-check-list">{checks.map(([key, value]) => <div className="mx-check" key={key}><CheckCircle2 size={16}/><span>{key.replaceAll("_", " ")}</span><b>{String(value)}</b></div>)}</div><div className="mx-evidence-note">Evidence is computed by the experiment engine. A missing result field is not treated as a passing invariant.</div><pre className="mx-result-json">{JSON.stringify(result, null, 2)}</pre></>}
      </section>
    </div>
    <section className="mx-panel mx-ledger"><div className="mx-section-title compact"><div><span className="mx-kicker">04 / EXECUTION TRACE</span><h2>Message timeline & decision inspector</h2><p>Select an executed event to inspect the exact fields recorded by the backend.</p></div><div className="mx-progress">{run ? Math.round((run.current_step / Math.max(1, run.trace.length)) * 100) : 0}%</div></div>
      <div className="mx-progress-track"><i style={{ width: `${run ? (run.current_step / Math.max(1, run.trace.length)) * 100 : 0}%` }}/></div>
      <div className="mx-ledger-grid"><div className="mx-event-list">{(run?.trace || []).map(item => <button key={item.step} disabled={item.step > (run?.current_step || 0)} onClick={() => setSelectedStep(item.step)} className={`mx-event ${selectedStep === item.step ? "active" : ""} ${item.step > (run?.current_step || 0) ? "future" : ""}`}><span className="mx-event-step">{String(item.step).padStart(2, "0")}</span><span className="mx-event-copy"><b>{item.event.replaceAll(".", " · ")}</b><small>{String(item.process || item.sender || item.node || item.message_id || "protocol engine")}</small></span><span className="mx-event-status">{item.step <= (run?.current_step || 0) ? "EXECUTED" : "PENDING"}</span></button>)}</div>
        <aside className="mx-inspector"><div className="mx-inspector-head"><Clock3 size={17}/><div><b>Selected event</b><small>{event ? `Trace step ${event.step}` : "No executed event selected"}</small></div></div>{event ? <><h3>{event.event.replaceAll(".", " · ")}</h3><dl>{Object.entries(event).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? <code>{JSON.stringify(value)}</code> : String(value)}</dd></div>)}</dl></> : <div className="mx-empty">Advance the trace, then select an executed event to see message sender, receiver, timestamp, decision and reason when provided by the backend.</div>}</aside>
      </div>
    </section>
    <section className="mx-panel mx-operation"><div className="mx-section-title compact"><div><span className="mx-kicker">05 / PROTECTED APPLICATION OPERATIONS</span><h2>Incident state & operation audit</h2><p>Illustrative application actions are shown only when present in the executed trace/result; they are not presented as live incident mutations.</p></div></div>
      <div className="mx-operations-grid"><div className="mx-operation-card"><span>BEFORE</span><b>Incident: INC-1042</b><small>Teaching fixture · status OPEN</small><code>owner = none</code></div><div className="mx-operation-arrow">→</div><div className="mx-operation-card"><span>INSIDE CRITICAL SECTION</span><b>Acknowledge · assign UNIT-7</b><small>Only the granted process may execute protected operations in the model.</small><code>reserve inventory → record audit</code></div><div className="mx-operation-arrow">→</div><div className="mx-operation-card"><span>AFTER RELEASE</span><b>Resource becomes available</b><small>Next eligible process may enter after permission rules allow it.</small><code>owner = none</code></div></div>
    </section>
    <footer className="mx-disclaimer"><ShieldCheck size={16}/><span><b>Correctness boundary:</b> this is a deterministic educational Ricart–Agrawala-style simulation. It does not acquire a distributed production lock, mutate the real incident database, or guarantee safety under arbitrary crashes/network partitions. For production reservation, use a database-enforced atomic claim or a consensus-backed lease with fencing.</span></footer>
  </main>;
}
