import { useMemo, useState } from "react";
import { Activity, AlertTriangle, ArrowUpRight, Check, ChevronDown, ChevronRight, CircleHelp, Clock3, Download, Play, RotateCcw, Server, ShieldCheck, SlidersHorizontal, StepForward, Workflow, Zap } from "lucide-react";
import "./physical-clock-lab.css";

type NodeClock = { id: string; label: string; role: string; offset: number; delay: number; available: boolean };
type Stage = "ready" | "collect" | "estimate" | "distribute" | "apply" | "verify";
type TraceEvent = { id: number; stage: Stage; title: string; detail: string; node?: string; kind: "system" | "message" | "warning" | "success"; payload: Record<string, unknown> };
const initialNodes: NodeClock[] = [
  { id: "n1", label: "Coordinator", role: "Incident intake", offset: 120, delay: 18, available: true },
  { id: "n2", label: "Node 02", role: "Dispatch service", offset: -35, delay: 26, available: true },
  { id: "n3", label: "Node 03", role: "Resource service", offset: 65, delay: 42, available: true },
  { id: "n4", label: "Node 04", role: "Event worker", offset: -10, delay: 31, available: true },
  { id: "n5", label: "Node 05", role: "Monitoring service", offset: 40, delay: 55, available: true },
];
const stages: { id: Stage; title: string; subtitle: string }[] = [
  { id: "collect", title: "Collect readings", subtitle: "Poll participating nodes and record round-trip delay" },
  { id: "estimate", title: "Estimate reference", subtitle: "Calculate a target from accepted clock observations" },
  { id: "distribute", title: "Distribute corrections", subtitle: "Send a signed correction instruction to each node" },
  { id: "apply", title: "Apply corrections", subtitle: "Advance each synthetic node clock by its instruction" },
  { id: "verify", title: "Verify convergence", subtitle: "Measure residual offsets and summarize the run" },
];
const presets = {
  drift: { label: "Uneven drift", offsets: [120, -35, 65, -10, 40] },
  disagreement: { label: "High disagreement", offsets: [180, -90, 45, -25, 5] },
  aligned: { label: "Nearly aligned", offsets: [12, -8, 5, -4, 2] },
};
type Preset = keyof typeof presets;
const ms = (n: number) => (n > 0 ? "+" : "") + n + " ms";

export function PhysicalClockLab({ onBack }: { onBack: () => void }) {
  const [nodes, setNodes] = useState<NodeClock[]>(initialNodes);
  const [preset, setPreset] = useState<Preset>("drift");
  const [delayModel, setDelayModel] = useState(30);
  const [maxCorrection, setMaxCorrection] = useState(250);
  const [stage, setStage] = useState<Stage>("ready");
  const [runTarget, setRunTarget] = useState<number | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [selectedNode, setSelectedNode] = useState("n2");
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [runId, setRunId] = useState(0);
  const [showSettings, setShowSettings] = useState(true);
  const [notice, setNotice] = useState("");
  const accepted = nodes.filter(n => n.available);
  const currentMean = accepted.length ? Math.round(accepted.reduce((sum, n) => sum + n.offset, 0) / accepted.length) : 0;
  const estimate = stage === "ready" || runTarget === null ? currentMean : runTarget;
  const readings = nodes.map(n => ({ ...n, target: estimate, requested: Math.max(-maxCorrection, Math.min(maxCorrection, estimate - n.offset)), corrected: stage === "apply" || stage === "verify" ? n.offset + Math.max(-maxCorrection, Math.min(maxCorrection, estimate - n.offset)) : null }));
  const selected = readings.find(n => n.id === selectedNode) || readings[0];
  const activeEvent = trace.find(e => e.id === selectedEvent) || trace[trace.length - 1];
  const completed = stage === "verify";
  const progress = stage === "ready" ? 0 : stages.findIndex(s => s.id === stage) + 1;
  const maxDisagreement = accepted.length ? Math.max(...accepted.map(n => n.offset)) - Math.min(...accepted.map(n => n.offset)) : 0;
  const avgAbsBefore = accepted.length ? Math.round(accepted.reduce((s, n) => s + Math.abs(n.offset - estimate), 0) / accepted.length) : 0;
  const avgAbsAfter = accepted.length ? Math.round(accepted.reduce((s, n) => s + Math.abs((n.corrected ?? n.offset) - estimate), 0) / accepted.length) : 0;
  const incidentRows = useMemo(() => [
    { service: "Incident intake", event: "incident.created", raw: 1000 + nodes[0].offset, corrected: 1000 + (stage === "apply" || stage === "verify" ? nodes[0].offset : nodes[0].offset + Math.max(-maxCorrection, Math.min(maxCorrection, estimate - nodes[0].offset))), node: nodes[0].id },
    { service: "Dispatch service", event: "unit.assignment.created", raw: 1120 + nodes[1].offset, corrected: 1120 + (stage === "apply" || stage === "verify" ? nodes[1].offset : nodes[1].offset + Math.max(-maxCorrection, Math.min(maxCorrection, estimate - nodes[1].offset))), node: nodes[1].id },
    { service: "Event worker", event: "worker.processed", raw: 1190 + nodes[3].offset, corrected: 1190 + (stage === "apply" || stage === "verify" ? nodes[3].offset : nodes[3].offset + Math.max(-maxCorrection, Math.min(maxCorrection, estimate - nodes[3].offset))), node: nodes[3].id },
  ], [nodes, stage, estimate, maxCorrection]);

  function addEvent(event: Omit<TraceEvent, "id">) {
    const id = trace.length + 1;
    setTrace(previous => [...previous, { ...event, id }]);
    setSelectedEvent(id);
  }
  function reset(nextPreset: Preset = preset) {
    const values = presets[nextPreset].offsets;
    setNodes(initialNodes.map((n, i) => ({ ...n, offset: values[i], available: true })));
    setPreset(nextPreset); setStage("ready"); setRunTarget(null); setTrace([]); setSelectedEvent(null); setRunId(v => v + 1);
    setNotice("Scenario reset. No clock corrections have been applied.");
  }
  function configurePreset(value: Preset) { reset(value); }
  function start() {
    const nextRun = runId + 1;
    const events: Omit<TraceEvent, "id">[] = [{ stage: "collect", title: "Synchronization round opened", detail: "Coordinator created a new round and will poll each available node.", kind: "system", payload: { run: nextRun, participant_count: accepted.length, delay_model_ms: delayModel } }, ...nodes.map(n => ({ stage: "collect" as Stage, title: n.available ? "Clock reading received" : "Node timed out", detail: n.available ? n.label + " reported offset " + ms(n.offset) + "; configured node delay " + n.delay + " ms." : n.label + " did not respond and is excluded from this round.", node: n.id, kind: (n.available ? "message" : "warning") as TraceEvent["kind"], payload: { node_id: n.id, reported_offset_ms: n.offset, configured_delay_ms: n.delay, configured_delay_model_ms: delayModel, accepted: n.available } }))];
    const fullTrace = events.map((event, i) => ({ ...event, id: i + 1 }));
    setTrace(fullTrace); setSelectedEvent(fullTrace[fullTrace.length - 1]?.id ?? null); setRunTarget(null); setStage("collect"); setRunId(nextRun);
    setNotice("Run started. The coordinator collected synthetic node readings.");
  }
  function advance() {
    if (stage === "ready") { start(); return; }
    if (stage === "collect") {
      setRunTarget(estimate); setStage("estimate");
      addEvent({ stage: "estimate", title: "Reference estimate calculated", detail: "The simplified model averages accepted synthetic offsets. Network-delay compensation is shown separately and is not silently inferred.", kind: "system", payload: { accepted_nodes: accepted.map(n => n.id), offsets_ms: accepted.map(n => n.offset), sum_ms: accepted.reduce((s, n) => s + n.offset, 0), count: accepted.length, mean_offset_ms: estimate } });
      setNotice("Readings collected. Inspect the accepted set and computed estimate.");
    } else if (stage === "estimate") {
      setStage("distribute");
      nodes.forEach(n => addEvent({ stage: "distribute", title: n.available ? "Correction instruction prepared" : "Correction skipped", detail: n.available ? n.label + " receives " + ms(Math.max(-maxCorrection, Math.min(maxCorrection, estimate - n.offset))) + " toward the estimated reference." : n.label + " is unavailable; no instruction was sent.", node: n.id, kind: n.available ? "message" : "warning", payload: { node_id: n.id, current_offset_ms: n.offset, target_offset_ms: estimate, requested_correction_ms: estimate - n.offset, applied_limit_ms: maxCorrection, sent: n.available } }));
      setNotice("Correction instructions generated from the run's calculated target.");
    } else if (stage === "distribute") {
      setNodes(previous => previous.map(n => n.available ? { ...n, offset: n.offset + Math.max(-maxCorrection, Math.min(maxCorrection, estimate - n.offset)) } : n));
      setStage("apply");
      addEvent({ stage: "apply", title: "Corrections applied to model state", detail: "Available synthetic clocks were updated by the bounded correction. This changes the lab model only, never the operating-system clock.", kind: "success", payload: { target_offset_ms: estimate, max_correction_ms: maxCorrection, applied_nodes: accepted.map(n => n.id) } });
      setNotice("Synthetic node states updated. Advance once more to verify residual disagreement.");
    } else if (stage === "apply") {
      setStage("verify");
      addEvent({ stage: "verify", title: "Post-correction verification complete", detail: "Residual disagreement is computed from the current modeled offsets. Unavailable nodes remain excluded.", kind: "success", payload: { accepted_nodes: accepted.map(n => n.id), offsets_after_ms: nodes.filter(n => n.available).map(n => n.offset), max_disagreement_ms: Math.max(...nodes.filter(n => n.available).map(n => n.offset)) - Math.min(...nodes.filter(n => n.available).map(n => n.offset)), mean_absolute_distance_from_target_ms: Math.round(nodes.filter(n => n.available).reduce((s, n) => s + Math.abs(n.offset - estimate), 0) / Math.max(1, accepted.length)) } });
      setNotice("Verification complete. Review the before/after metrics and event evidence.");
    }
  }
  function toggleNode(id: string) {
    setNodes(previous => previous.map(n => n.id === id ? { ...n, available: !n.available } : n));
    setNotice("Node availability changed. Reset or start a new run to apply the scenario change.");
    setStage("ready"); setRunTarget(null); setTrace([]); setSelectedEvent(null);
  }
  function updateOffset(id: string, value: number) {
    setNodes(previous => previous.map(n => n.id === id ? { ...n, offset: value } : n));
    setStage("ready"); setRunTarget(null); setTrace([]); setSelectedEvent(null);
    setNotice("Clock offset updated. Start a new run to capture the changed input.");
  }
  const statusLabel = completed ? "VERIFIED" : stage === "ready" ? "READY" : "RUNNING";
  return <div className="pcl-page">
    <header className="pcl-header">
      <div className="pcl-heading"><div className="pcl-mark"><Clock3 size={22}/></div><div><div className="pcl-eyebrow">AEGISGRID / DISTRIBUTED RUNTIME / LAB 01</div><h1>Physical Clock Synchronization</h1><p>Berkeley-style coordinator averaging · interactive execution studio</p></div></div>
      <div className="pcl-head-actions"><span className={"pcl-status " + (completed ? "is-done" : "")}><i/>{statusLabel}</span><button className="pcl-btn secondary" onClick={onBack}><Workflow size={14}/> All labs</button><button className="pcl-btn secondary" onClick={() => { const content = JSON.stringify({ run_id: runId, stage, preset, delay_model_ms: delayModel, max_correction_ms: maxCorrection, nodes, trace }, null, 2); const blob = new Blob([content], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "aegisgrid-clock-run-" + runId + ".json"; a.click(); URL.revokeObjectURL(url); }}><Download size={14}/> Export trace</button></div>
    </header>
    <div className="pcl-notice"><Activity size={15}/><span>{notice || "Deterministic educational simulation · synthetic offsets only · no host clock is read or changed."}</span><span className="pcl-sim-tag">SIMULATION</span></div>
    <section className="pcl-config">
      <div className="pcl-section-title"><div><span className="pcl-index">01</span><div><h2>Configure the environment</h2><p>Change inputs before a run; every output is calculated from this scenario.</p></div></div><button className="pcl-icon-button" onClick={() => setShowSettings(v => !v)} aria-expanded={showSettings}><SlidersHorizontal size={16}/><span>{showSettings ? "Hide controls" : "Show controls"}</span><ChevronDown size={14}/></button></div>
      {showSettings && <div className="pcl-config-grid">
        <label className="pcl-field"><span>Clock scenario</span><select value={preset} onChange={e => configurePreset(e.target.value as Preset)}><option value="drift">Uneven drift</option><option value="disagreement">High disagreement</option><option value="aligned">Nearly aligned</option></select><small>Preset loads a repeatable set of synthetic offsets.</small></label>
        <label className="pcl-field"><span>Coordinator node</span><select value="n1" disabled><option value="n1">Node 01 · Incident intake</option></select><small>Coordinator selection is fixed in this version.</small></label>
        <label className="pcl-field"><span>Network delay model <b>{delayModel} ms</b></span><input type="range" min="0" max="100" step="5" value={delayModel} onChange={e => { setDelayModel(Number(e.target.value)); setStage("ready"); setRunTarget(null); setTrace([]); }}/><small>Used as the scenario's configured delay context; no unimplemented compensation is implied.</small></label>
        <label className="pcl-field"><span>Maximum correction magnitude <b>{maxCorrection} ms</b></span><input type="range" min="25" max="250" step="25" value={maxCorrection} onChange={e => { setMaxCorrection(Number(e.target.value)); setStage("ready"); setRunTarget(null); setTrace([]); }}/><small>Bounds each signed correction to avoid an unbounded jump.</small></label>
      </div>}
      <div className="pcl-control-row"><div className="pcl-control-copy"><b>Execution controls</b><span>{stage === "ready" ? "Ready to begin a new round" : "Stage " + progress + " of 5 · " + (stages.find(s => s.id === stage)?.title || "Ready")}</span></div><button className="pcl-btn primary" onClick={start}><Play size={15}/> {stage === "ready" ? "Start new run" : "Restart run"}</button><button className="pcl-btn secondary" disabled={stage === "verify"} onClick={advance}><StepForward size={15}/> {stage === "ready" ? "Begin / next stage" : stage === "apply" ? "Verify results" : "Next stage"}</button><button className="pcl-btn secondary" onClick={() => reset()}><RotateCcw size={14}/> Reset scenario</button></div>
    </section>
    <div className="pcl-metrics">
      <div className="pcl-metric"><span>Participating nodes</span><b>{accepted.length}<small> / {nodes.length}</small></b><div className="pcl-meter"><i style={{width: (accepted.length / nodes.length * 100) + "%"}}/></div></div>
      <div className="pcl-metric"><span>Estimated reference offset</span><b>{stage === "ready" || progress < 2 ? "—" : ms(estimate)}</b><small>{stage === "ready" || progress < 2 ? "Calculated after collection" : "Mean of accepted synthetic offsets"}</small></div>
      <div className="pcl-metric"><span>Mean absolute distance</span><b>{completed ? avgAbsAfter : avgAbsBefore}<small> ms</small></b><small>{completed ? "After correction" : "Before correction · relative to target"}</small></div>
      <div className="pcl-metric"><span>Max node disagreement</span><b>{completed ? maxDisagreement : Math.max(...accepted.map(n => n.offset)) - Math.min(...accepted.map(n => n.offset))}<small> ms</small></b><small>{completed ? "Residual spread" : "Initial spread among available nodes"}</small></div>
    </div>
    <div className="pcl-main-grid">
      <section className="pcl-panel pcl-topology"><div className="pcl-panel-head"><div><span className="pcl-index">02</span><div><h2>Distributed clock topology</h2><p>Select a node to inspect its readings and correction.</p></div></div><span className="pcl-count">{accepted.length} available</span></div>
        <div className="pcl-topology-canvas"><div className="pcl-grid-bg"/><svg className="pcl-links" viewBox="0 0 600 280" preserveAspectRatio="none" aria-hidden="true"><path d="M300 45 L100 130 L300 230 L500 130 Z M300 45 L300 230 M100 130 L500 130" fill="none" stroke="#31506a" strokeWidth="1.5" strokeDasharray="5 6"/></svg>
          {readings.map((n, i) => <button key={n.id} className={"pcl-node n" + i + (selectedNode === n.id ? " selected" : "") + (!n.available ? " unavailable" : "")} onClick={() => setSelectedNode(n.id)}><span className="pcl-node-icon">{n.available ? (i === 0 ? <ShieldCheck size={17}/> : <Server size={17}/>) : <AlertTriangle size={17}/>}</span><b>{n.label}</b><small>{n.role}</small><strong>{ms(n.offset)}</strong><em>{n.available ? (i === 0 ? "COORDINATOR" : "RESPONDING") : "UNAVAILABLE"}</em></button>)}
        </div>
        <div className="pcl-node-inspector"><div className="pcl-inspector-head"><div><span>SELECTED NODE</span><h3>{selected?.label}</h3><small>{selected?.role} · {selected?.id}</small></div><button className="pcl-btn secondary compact" onClick={() => toggleNode(selected.id)}><Zap size={13}/>{selected.available ? "Simulate timeout" : "Restore node"}</button></div>
          <div className="pcl-node-facts"><div><span>Current offset</span><b>{ms(selected.offset)}</b></div><div><span>Configured delay</span><b>{selected.delay + delayModel} ms</b></div><div><span>Requested correction</span><b>{selected.available && stage !== "ready" ? ms(Math.max(-maxCorrection, Math.min(maxCorrection, estimate - selected.offset))) : "Pending"}</b></div><div><span>State</span><b>{selected.available ? "Available" : "Excluded"}</b></div></div>
          <label className="pcl-field pcl-offset-field"><span>Edit synthetic offset <b>{ms(selected.offset)}</b></span><input type="range" min="-200" max="200" step="5" value={selected.offset} onChange={e => updateOffset(selected.id, Number(e.target.value))}/><small>Changing a clock offset invalidates the previous trace and requires a new run.</small></label>
        </div>
      </section>
      <section className="pcl-panel pcl-pipeline"><div className="pcl-panel-head"><div><span className="pcl-index">03</span><div><h2>Execution pipeline</h2><p>Each stage creates inspectable evidence.</p></div></div></div>
        <div className="pcl-stage-list">{stages.map((s, i) => { const current = s.id === stage; const done = stages.findIndex(x => x.id === stage) > i || completed; return <div key={s.id} className={"pcl-stage " + (current ? "current" : "") + (done ? " done" : "")}><span className="pcl-stage-num">{done ? <Check size={14}/> : String(i + 1).padStart(2, "0")}</span><div><b>{s.title}</b><small>{s.subtitle}</small></div><span className="pcl-stage-state">{done ? "DONE" : current ? "ACTIVE" : "WAITING"}</span></div>; })}</div>
        <div className="pcl-pipeline-foot"><div><span>Round progress</span><b>{Math.round(progress / 5 * 100)}%</b></div><div className="pcl-progress"><i style={{width: (progress / 5 * 100) + "%"}}/></div><button className="pcl-btn primary full" onClick={advance} disabled={completed}><StepForward size={15}/>{stage === "ready" ? "Begin experiment" : completed ? "Experiment verified" : "Execute next stage"}</button><p>Step controls advance the model deterministically; no hidden background execution occurs.</p></div>
      </section>
    </div>
    <div className="pcl-lower-grid">
      <section className="pcl-panel"><div className="pcl-panel-head"><div><span className="pcl-index">04</span><div><h2>Clock correction ledger</h2><p>Inputs, target and signed adjustment for every participant.</p></div></div></div>
        <div className="pcl-table-wrap"><table className="pcl-table"><thead><tr><th>NODE</th><th>INITIAL OFFSET</th><th>ESTIMATE</th><th>REQUESTED ADJUSTMENT</th><th>MODELED OFFSET</th><th>STATUS</th></tr></thead><tbody>{readings.map(n => <tr key={n.id} className={selectedNode === n.id ? "row-selected" : ""} onClick={() => setSelectedNode(n.id)}><td><b>{n.label}</b><small>{n.role}</small></td><td className={n.offset > 0 ? "positive" : "negative"}>{ms(n.offset)}</td><td>{stage === "ready" || progress < 2 ? "—" : ms(estimate)}</td><td>{n.available && stage !== "ready" ? ms(Math.max(-maxCorrection, Math.min(maxCorrection, estimate - n.offset))) : "—"}</td><td>{n.available ? ms(n.offset) : "Excluded"}</td><td><span className={"pcl-pill " + (n.available ? completed ? "good" : "neutral" : "warn")}>{!n.available ? "EXCLUDED" : completed ? "VERIFIED" : "AVAILABLE"}</span></td></tr>)}</tbody></table></div>
        <div className="pcl-table-note"><CircleHelp size={14}/><span>Corrections are bounded. If the maximum correction is too small, nodes may not converge in one round; run again to inspect the residual.</span></div>
      </section>
      <section className="pcl-panel pcl-trace-panel"><div className="pcl-panel-head"><div><span className="pcl-index">05</span><div><h2>Execution event ledger</h2><p>Choose an event to inspect its payload.</p></div></div><span className="pcl-count">{trace.length} events</span></div>
        <div className="pcl-trace-list">{trace.length ? trace.map(e => <button key={e.id} className={"pcl-trace-row " + (selectedEvent === e.id ? "selected" : "")} onClick={() => setSelectedEvent(e.id)}><span className={"pcl-trace-icon " + e.kind}>{e.kind === "warning" ? <AlertTriangle size={14}/> : e.kind === "success" ? <Check size={14}/> : e.kind === "message" ? <ArrowUpRight size={14}/> : <Activity size={14}/>}</span><span className="pcl-trace-copy"><b>{e.title}</b><small>Step {e.id} · {e.node || e.stage}</small></span><ChevronRight size={14}/></button>) : <div className="pcl-empty"><Activity size={20}/><b>No run trace yet</b><span>Start a run to create timestamped protocol events.</span></div>}</div>
        {activeEvent && <div className="pcl-event-detail"><div><span>SELECTED EVENT / {activeEvent.stage.toUpperCase()}</span><b>{activeEvent.title}</b><p>{activeEvent.detail}</p></div><pre>{JSON.stringify(activeEvent.payload, null, 2)}</pre></div>}
      </section>
    </div>
    <section className="pcl-panel pcl-impact"><div className="pcl-panel-head"><div><span className="pcl-index">06</span><div><h2>AegisGrid incident timeline impact</h2><p>Synthetic service events illustrate how differing clocks can mislead wall-clock ordering.</p></div></div><span className="pcl-sim-tag">ILLUSTRATIVE DATA</span></div>
      <div className="pcl-impact-callout"><AlertTriangle size={17}/><p>Corrected times are estimates derived from this lab's modeled offsets. They are not replacements for message IDs, event causality or production timestamps.</p></div>
      <div className="pcl-table-wrap"><table className="pcl-table"><thead><tr><th>SERVICE</th><th>EVENT</th><th>RAW SYNTHETIC TIME</th><th>MODELED TIME</th><th>INTERPRETATION</th></tr></thead><tbody>{incidentRows.map(row => <tr key={row.event}><td><b>{row.service}</b></td><td><code>{row.event}</code></td><td>{row.raw} ms</td><td>{completed ? row.corrected + " ms" : "Run corrections to compare"}</td><td>{row.raw > 1100 ? "Clock offset may distort apparent order" : "Reference event"}</td></tr>)}</tbody></table></div>
    </section>
    <footer className="pcl-footer"><ShieldCheck size={16}/><span><b>Integrity note</b> — this is a deterministic local simulation. It does not read or modify host clocks, and delay is recorded as scenario metadata rather than treated as measured network telemetry.</span><button onClick={() => { const content = JSON.stringify({ run_id: runId, stage, preset, nodes, trace }, null, 2); navigator.clipboard?.writeText(content).then(() => setNotice("Run evidence copied to clipboard.")).catch(() => setNotice("Clipboard unavailable; use Export trace.")); }}><Download size={13}/> Copy evidence</button></footer>
  </div>;
}
