import { Activity, ArrowLeftRight, CheckCircle2, CircleDashed, Code2, Database, GitBranch, Layers3, Network, Radio, Server, ShieldAlert, Terminal, Workflow } from "lucide-react";
import { CommunicationDemo } from "./CommunicationDemo";
import "./communication-control-room.css";

const transports = [
  { id: "rpc", title: "Remote Procedure Call", short: "RPC", state: "Design target", description: "Caller invokes a remote operation and inspects request, response, duration and errors.", icon: Code2 },
  { id: "messaging", title: "Message-oriented", short: "BROKER", state: "Interactive lab", description: "Discrete messages, queueing, delivery attempts, acknowledgement and retry.", icon: Workflow },
  { id: "stream", title: "Stream-oriented", short: "STREAM", state: "Interactive lab", description: "Ordered byte flow, buffering, consumer lag, interruption and recovery.", icon: Radio },
  { id: "p2p", title: "Peer-to-peer messaging", short: "P2P", state: "Transport not yet verified", description: "Peer identity, direct versus relayed route, connection state and delivery receipt.", icon: Network },
  { id: "webrtc", title: "WebRTC", short: "WEBRTC", state: "Transport not yet verified", description: "Signalling, SDP/ICE negotiation, peer connection and data-channel delivery.", icon: ArrowLeftRight }
];

export function CommunicationControlRoom({ onBack }: { onBack: () => void }) {
  return <main className="communication-control-room">
    <header className="ccr-hero">
      <div className="ccr-hero-copy">
        <div className="ccr-eyebrow"><Activity size={14}/> AEGISGRID / DISTRIBUTED SYSTEMS / COMMUNICATION</div>
        <h1>Communication Control Room</h1>
        <p>Trace an incident-response communication through its sender, transport, receiver and processing evidence. Each transport keeps its own semantics and verification boundary.</p>
        <div className="ccr-hero-meta"><span><Database size={13}/> Incident context: INC-1042 teaching fixture</span><span><ShieldAlert size={13}/> Simulation and runtime evidence are never conflated</span></div>
      </div>
      <button className="ccr-back" onClick={onBack}><ArrowLeftRight size={15}/> Back to experiments</button>
    </header>

    <section className="ccr-status-strip">
      <div><span className="ccr-status-dot simulation"/><div><b>Message / stream labs</b><small>Deterministic experiment traces</small></div></div>
      <div><span className="ccr-status-dot pending"/><div><b>Docker log correlation</b><small>Requires structured runtime evidence</small></div></div>
      <div><span className="ccr-status-dot pending"/><div><b>RPC / P2P / WebRTC</b><small>Separate transport implementation required</small></div></div>
    </section>

    <section className="ccr-transport-section">
      <div className="ccr-section-title"><div><span>01 / TRANSPORT CATALOGUE</span><h2>Choose the communication model</h2><p>Available labs open below. Other transport cards document the intended contract without pretending a transport is already implemented.</p></div><Layers3 size={21}/></div>
      <div className="ccr-transport-grid">{transports.map((t) => { const Icon=t.icon; const active=t.id==="messaging"||t.id==="stream"; return <article key={t.id} className={`ccr-transport-card ${active?"available":"planned"}`}><div className="ccr-card-top"><span className="ccr-transport-icon"><Icon size={19}/></span><span className={`ccr-transport-state ${active?"ready":"pending"}`}>{active?<CheckCircle2 size={12}/>:<CircleDashed size={12}/>} {t.state}</span></div><div className="ccr-transport-short">{t.short}</div><h3>{t.title}</h3><p>{t.description}</p><div className="ccr-card-footer"><span>{active?"Open interactive experiment":"Implementation boundary"}</span>{active&&<span className="ccr-arrow">↘</span>}</div></article>})}</div>
    </section>

    <section className="ccr-runtime-note">
      <div className="ccr-runtime-icon"><Terminal size={19}/></div>
      <div><b>Evidence integrity</b><p>The current message and stream experiments are deterministic simulations. They do not prove that a particular action travelled through Docker, RabbitMQ or a live WebSocket. Runtime mode should only be enabled after correlation IDs, structured service logs and a restricted log-evidence endpoint are implemented and tested.</p></div>
    </section>

    <section className="ccr-lab-shell">
      <div className="ccr-section-title"><div><span>02 / INTERACTIVE EXECUTION</span><h2>Message and stream experiments</h2><p>Use the existing persisted experiment API to configure, step through, inspect and export the event trace.</p></div><Server size={21}/></div>
      <CommunicationDemo onBack={onBack}/>
    </section>
    <footer className="ccr-footer"><GitBranch size={15}/><span>Mutual Exclusion and Beacon Protocol Control Room are independent labs. This workspace focuses on communication semantics and transport evidence.</span></footer>
  </main>;
}
