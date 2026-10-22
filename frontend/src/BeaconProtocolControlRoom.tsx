import { useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Clock3, Download, Play, Radio, RotateCcw, ShieldAlert, SkipForward, Wifi, WifiOff } from "lucide-react";
import "./beacon-protocol-control-room.css";

const API = (import.meta as ImportMeta & { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL || "/api-proxy";
type TraceEvent = { step: number; at_ms?: number; event: string; node?: string; detail?: string; actual_state?: string; observed_state?: string; elapsed_since_heartbeat_ms?: number; last_received_ms?: number; [key: string]: unknown };
type ExperimentRun = { id: number; lab_id: string; scenario: string; parameters: Record<string, unknown>; trace: TraceEvent[]; result: Record<string, unknown>; status: string; current_step: number; created_at: string };
type FaultMode = "crash" | "partition" | "delay" | "recovery";
const modes: { id: FaultMode; title: string; description: string }[] = [
  { id: "crash", title: "Worker crash", description: "The process stops emitting beacons; the observer sees silence." },
  { id: "partition", title: "Network partition", description: "The worker may still run, but its messages cannot reach the observer." },
  { id: "delay", title: "Delayed beacons", description: "Messages are delayed in transit and may arrive after the timeout." },
  { id: "recovery", title: "Intermittent loss + recovery", description: "The trace includes missed beats followed by a valid recovery beacon." }
];
const fmt = (v: unknown) => v === undefined || v === null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
const titleCase = (v: string) => v.replaceAll(".", " · ").replaceAll("_", " ");
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init });
  if (!response.ok) throw new Error((await response.text()).slice(0, 260) || `HTTP ${response.status}`);
  return response.json();
}
export function BeaconProtocolControlRoom() {
  const [faultMode, setFaultMode] = useState<FaultMode>("crash");
  const [nodeId, setNodeId] = useState("dispatch-worker-01");
  const [intervalMs, setIntervalMs] = useState(1000);
  const [timeoutMs, setTimeoutMs] = useState(3000);
  const [missedBeats, setMissedBeats] = useState(5);
  const [networkDelayMs, setNetworkDelayMs] = useState(1800);
  const [packetLoss, setPacketLoss] = useState(20);
  const [includeRecovery, setIncludeRecovery] = useState(true);
  const [run, setRun] = useState<ExperimentRun | null>(null);
  const [selectedStep, setSelectedStep] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const executed = run?.trace.filter(e => e.step <= run.current_step) || [];
  const selectedEvent = selectedStep === null ? executed[executed.length - 1] : executed.find(e => e.step === selectedStep);
  const finalState = run?.result.observed_state || run?.result.final_state || "not started";
  const currentObservedState = selectedEvent?.observed_state || (executed.length ? executed[executed.length - 1].observed_state : "healthy") || "healthy";
  const lastEvent = executed[executed.length - 1];
  const currentAge = lastEvent?.elapsed_since_heartbeat_ms ?? 0;
  const suspected = executed.some(e => e.event === "failure.suspected");
  const received = executed.filter(e => e.event === "heartbeat.received" || e.event === "heartbeat.recovered").length;
  const missed = executed.filter(e => e.event === "heartbeat.missed").length;
  const detectionEvent = executed.find(e => e.event === "failure.suspected");
  const progress = run ? Math.round(run.current_step / Math.max(1, run.trace.length) * 100) : 0;
  const healthColor = String(currentObservedState).toLowerCase() === "suspected" ? "danger" : String(currentObservedState).toLowerCase() === "healthy" ? "success" : "neutral";
  const nodeStates = useMemo(() => [
    { id: "coordinator", name: "Incident Coordinator", subtitle: "Observer · INC-1042", state: "observing" },
    { id: "worker", name: nodeId, subtitle: "Beacon source · response task", state: String(currentObservedState) },
    { id: "allocator", name: "Resource Allocator", subtitle: "Assignment policy consumer", state: suspected ? "review flagged" : "standing by" }
  ], [nodeId, currentObservedState, suspected]);

  async function createRun() {
    setBusy(true); setError(""); setNotice(""); setSelectedStep(null);
    try {
      const response = await api<{ run: ExperimentRun }>("/experiments", { method: "POST", body: JSON.stringify({
        lab_id: "beacon", scenario: faultMode, parameters: {
          node_id: nodeId, interval_ms: intervalMs, timeout_ms: timeoutMs, threshold: Math.max(1, Math.ceil(timeoutMs / intervalMs)),
          missed_beats: missedBeats, network_delay_ms: networkDelayMs, packet_loss_percent: packetLoss,
          fault_mode: faultMode, recover: includeRecovery
        }
      }) });
      setRun(response.run);
      setNotice("A persisted beacon experiment was created. Advance the event ledger to observe the detector's decisions.");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to create beacon experiment"); }
    finally { setBusy(false); }
  }
  async function step() {
    if (!run || run.current_step >= run.trace.length) return;
    setBusy(true); setError("");
    try { const response = await api<{ run: ExperimentRun }>(`/experiments/${run.id}/step`, { method: "POST" }); setRun(response.run); setSelectedStep(response.run.current_step); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to advance event"); }
    finally { setBusy(false); }
  }
  async function runAll() {
    if (!run) return;
    setBusy(true); setError("");
    try {
      let latest = run;
      while (latest.current_step < latest.trace.length) {
        const response = await api<{ run: ExperimentRun }>(`/experiments/${latest.id}/step`, { method: "POST" });
        latest = response.run;
      }
      setRun(latest); setSelectedStep(latest.current_step); setNotice("Trace completed. Review suspicion timing and recovery evidence.");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to finish run"); }
    finally { setBusy(false); }
  }
  async function pauseResume() {
    if (!run) return;
    const action = run.status === "paused" ? "resume" : "pause";
    setBusy(true); setError("");
    try { const response = await api<{ run: ExperimentRun }>(`/experiments/${run.id}/${action}`, { method: "POST" }); setRun(response.run); setNotice(action === "pause" ? "Experiment paused." : "Experiment resumed."); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to change run state"); }
    finally { setBusy(false); }
  }
  function exportEvidence() {
    if (!run) return;
    const evidence = { title: "AegisGrid Beacon Protocol Control Room", execution_mode: "deterministic simulation", incident: "INC-1042 (teaching fixture)", configuration: run.parameters, run, executed_trace: executed, exported_at: new Date().toISOString() };
    const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `aegisgrid-beacon-run-${run.id}.json`; link.click(); URL.revokeObjectURL(url);
  }

  return <main className="beacon-room">
    <header className="beacon-hero">
      <div><div className="beacon-eyebrow"><Radio size={14}/> DISTRIBUTED RUNTIME / FAILURE DETECTION</div><h1>Beacon Protocol Control Room</h1><p>Run a communication failure against a response worker, observe beacon delivery, and inspect why the coordinator marks a service healthy or suspected.</p></div>
      <div className="beacon-sim-badge"><span/> <div><b>DETERMINISTIC SIMULATION</b><small>No live worker is stopped or reassigned</small></div></div>
    </header>

    <section className="beacon-incident-banner">
      <div className="beacon-incident-icon"><ShieldAlert size={25}/></div>
      <div className="beacon-incident-copy"><span>ACTIVE TEACHING SCENARIO · INCIDENT INC-1042</span><h2>Dispatch communication health</h2><p>Observe whether a response worker can be reached before deciding whether its assignment needs review.</p></div>
      <div className="beacon-health"><span>OBSERVER CLASSIFICATION</span><strong className={healthColor}>{String(currentObservedState).toUpperCase()}</strong><small>{run ? `Run #${run.id} · ${run.status}` : "Waiting for experiment"}</small></div>
    </section>

    <section className="beacon-panel">
      <div className="beacon-section-heading"><div><span className="beacon-kicker">01 / EXPERIMENT CONFIGURATION</span><h2>Choose a failure mode</h2><p>All values configure the backend-generated beacon trace. No real process or network is modified.</p></div><Activity size={20}/></div>
      <div className="beacon-mode-grid">{modes.map(mode => <button key={mode.id} className={faultMode === mode.id ? "beacon-mode selected" : "beacon-mode"} onClick={() => { setFaultMode(mode.id); setRun(null); setSelectedStep(null); setNotice(""); }}><span>{mode.id === "crash" ? "01" : mode.id === "partition" ? "02" : mode.id === "delay" ? "03" : "04"}</span><b>{mode.title}</b><small>{mode.description}</small></button>)}</div>
      <div className="beacon-config-grid">
        <label>Monitored worker ID<input value={nodeId} onChange={e => setNodeId(e.target.value)} maxLength={80}/></label>
        <label>Beacon interval (ms)<input type="number" min={100} max={60000} step={100} value={intervalMs} onChange={e => setIntervalMs(Number(e.target.value))}/><small>Expected frequency of a beacon.</small></label>
        <label>Suspicion timeout (ms)<input type="number" min={100} max={180000} step={100} value={timeoutMs} onChange={e => setTimeoutMs(Number(e.target.value))}/><small>Silence duration before suspicion.</small></label>
        <label>Expected missed beats<input type="number" min={0} max={100} value={missedBeats} onChange={e => setMissedBeats(Number(e.target.value))}/><small>Number of simulated beacon slots.</small></label>
        <label>Network delay (ms)<input type="number" min={0} max={60000} step={100} value={networkDelayMs} onChange={e => setNetworkDelayMs(Number(e.target.value))}/><small>Used by delayed-beacon scenario.</small></label>
        <label>Packet loss (%)<input type="number" min={0} max={100} value={packetLoss} onChange={e => setPacketLoss(Number(e.target.value))}/><small>Optional loss injected into the trace.</small></label>
      </div>
      <label className="beacon-check"><input type="checkbox" checked={includeRecovery} onChange={e => setIncludeRecovery(e.target.checked)}/> Include a recovery beacon at the end of the run</label>
      <div className="beacon-toolbar"><div><b>{run ? `Run #${run.id} · ${run.status}` : "No run created"}</b><small>{run ? `Event cursor ${run.current_step} / ${run.trace.length}` : "Create a run to generate protocol events"}</small></div><div className="beacon-actions"><button className="beacon-btn primary" disabled={busy} onClick={() => void createRun()}><Play size={14}/> Create run</button><button className="beacon-btn" disabled={!run || busy || run.current_step >= run.trace.length} onClick={() => void step()}><SkipForward size={14}/> Next event</button><button className="beacon-btn" disabled={!run || busy || run.current_step >= run.trace.length} onClick={() => void runAll()}><Play size={14}/> Run to end</button><button className="beacon-btn" disabled={!run || busy || run.status === "completed"} onClick={() => void pauseResume()}>{run?.status === "paused" ? "Resume" : "Pause"}</button><button className="beacon-btn" disabled={!run} onClick={exportEvidence}><Download size={14}/> Export evidence</button><button className="beacon-btn" disabled={busy} onClick={() => {setRun(null);setSelectedStep(null);setNotice("Run cleared. Create a new run to reset the experiment.");}}><RotateCcw size={14}/> Reset</button></div></div>
      {notice && <div className="beacon-notice"><CheckCircle2 size={15}/>{notice}</div>}{error && <div className="beacon-error"><AlertTriangle size={15}/>{error}</div>}
    </section>

    <div className="beacon-main-grid">
      <section className="beacon-panel"><div className="beacon-section-heading compact"><div><span className="beacon-kicker">02 / RESPONSE TOPOLOGY</span><h2>Who can communicate?</h2></div><span className="beacon-count">3 logical services</span></div>
        <div className="beacon-topology">{nodeStates.map((node) => <div key={node.id} className={`beacon-node ${node.id === "worker" && suspected ? "suspected" : ""}`}><div className="beacon-node-symbol">{node.id === "worker" ? <Radio size={20}/> : node.id === "coordinator" ? <Activity size={20}/> : <Wifi size={20}/>}</div><div className="beacon-node-copy"><b>{node.name}</b><small>{node.subtitle}</small><span>{node.state}</span></div>{node.id === "worker" && suspected ? <WifiOff size={17}/> : <Wifi size={17}/>}</div>)}</div>
        <div className="beacon-link-state"><span className={suspected ? "link-line broken" : "link-line"}/><span>{suspected ? "Beacon silence observed · suspicion raised" : "Beacon path monitored by coordinator"}</span></div>
        <p className="beacon-footnote">Topology is conceptual; the event ledger is authoritative for delivery, timeout and state transitions.</p>
      </section>
      <section className="beacon-panel"><div className="beacon-section-heading compact"><div><span className="beacon-kicker">03 / DETECTOR TELEMETRY</span><h2>Evidence at a glance</h2></div><Clock3 size={19}/></div>
        <div className="beacon-metrics"><div><small>Received beacons</small><strong>{received}</strong></div><div><small>Missed slots</small><strong>{missed}</strong></div><div><small>Last silence age</small><strong>{currentAge} ms</strong></div><div><small>Detection time</small><strong>{detectionEvent ? `${detectionEvent.at_ms ?? "—"} ms` : "—"}</strong></div></div>
        <div className="beacon-explanation"><b>{suspected ? "Why is the worker suspected?" : "What is the detector observing?"}</b><p>{suspected ? `The event trace crossed the configured ${timeoutMs} ms silence timeout without an accepted beacon. This is suspicion, not proof of a process crash.` : "The observer tracks the last accepted beacon and compares elapsed silence with the configured timeout. The detector must not infer a crash merely from a slow or partitioned network."}</p></div>
        <div className="beacon-final-state"><span>Backend final classification</span><b>{String(finalState).toUpperCase()}</b></div>
      </section>
    </div>

    <section className="beacon-panel">
      <div className="beacon-section-heading"><div><span className="beacon-kicker">04 / EVENT EXECUTION</span><h2>Beacon timeline & event inspector</h2><p>Only executed events are inspectable. Future events remain pending until the cursor advances.</p></div><strong className="beacon-progress-label">{progress}%</strong></div>
      <div className="beacon-progress-track"><i style={{ width: progress + "%" }}/></div>
      {!run && <div className="beacon-empty">Choose a failure mode and create a run. The backend will return the ordered beacon/failure trace.</div>}
      {run && <div className="beacon-event-layout"><div className="beacon-events">{run.trace.map(item => <button key={item.step} disabled={item.step > run.current_step} onClick={() => setSelectedStep(item.step)} className={`beacon-event ${selectedStep === item.step ? "selected" : ""} ${item.step > run.current_step ? "pending" : ""}`}><span className="beacon-event-number">{String(item.step).padStart(2, "0")}</span><span className="beacon-event-copy"><b>{titleCase(item.event)}</b><small>t = {item.at_ms ?? "—"} ms · {item.node || nodeId}</small></span><span className="beacon-event-mark">{item.step <= run.current_step ? "EXECUTED" : "PENDING"}</span></button>)}</div>
        <aside className="beacon-inspector"><div className="beacon-inspector-heading"><Clock3 size={17}/><div><b>Event evidence</b><small>{selectedEvent ? `Step ${selectedEvent.step}` : "Select an executed event"}</small></div></div>{selectedEvent ? <><h3>{titleCase(selectedEvent.event)}</h3><p>{selectedEvent.detail || "Backend event recorded."}</p><dl>{Object.entries(selectedEvent).map(([key,value]) => <div key={key}><dt>{titleCase(key)}</dt><dd>{fmt(value)}</dd></div>)}</dl></> : <div className="beacon-empty">Advance the trace to inspect the event's timestamp, worker state, observer state and decision reason.</div>}</aside></div>}
    </section>

    <section className="beacon-panel"><div className="beacon-section-heading"><div><span className="beacon-kicker">05 / OPERATIONAL IMPACT</span><h2>Incident assignment review</h2><p>Detector output and operational policy are separate. This panel records a simulated review flag; it does not mutate real incident assignments.</p></div><ShieldAlert size={20}/></div>
      <div className="beacon-impact-grid"><div className="beacon-impact-card"><span>INCIDENT</span><b>INC-1042 · Active response</b><small>Teaching fixture linked to a dispatch communication scenario.</small></div><div className="beacon-impact-arrow">→</div><div className="beacon-impact-card"><span>DETECTOR OUTPUT</span><b>{suspected ? "Worker suspected" : "No suspicion recorded yet"}</b><small>{suspected ? "A timeout event is present in the executed trace." : "The worker remains under observation until evidence changes its state."}</small></div><div className="beacon-impact-arrow">→</div><div className="beacon-impact-card"><span>POLICY CONSEQUENCE</span><b>{suspected ? "Flag assignment for human review" : "Keep assignment unchanged"}</b><small>Simulation-only policy response; no live dispatch action is executed.</small></div></div>
    </section>

    <footer className="beacon-boundary"><ShieldAlert size={16}/><span><b>Correctness boundary:</b> this is a deterministic educational beacon/heartbeat failure detector. A timeout indicates that communication was not observed in time; it cannot alone distinguish a crashed worker from delayed packets or a network partition. Live dispatch resources are not stopped, reassigned or modified.</span></footer>
  </main>;
}
