import { useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Clock3, Download, Play, RotateCcw, Save, StepForward, Network, Radio, ChevronLeft } from "lucide-react";

const API = (import.meta as ImportMeta & {env?: {VITE_API_URL?: string}}).env?.VITE_API_URL || "/api-proxy";
type ClockEvent = { step:number; event:string; [key:string]:unknown };
type ClockRun = { id:number; lab_id:string; scenario:string; parameters:Record<string,unknown>; trace:ClockEvent[]; result:Record<string,unknown>; status:string; current_step:number; created_at:string };
async function request<T>(path:string, init?:RequestInit):Promise<T>{
 const response=await fetch(API+path,{headers:{"Content-Type":"application/json",...(init?.headers||{})},...init});
 if(!response.ok) throw new Error((await response.text()).slice(0,260)||("HTTP "+response.status));
 return response.json();
}
const defaults=[120,40,-60,200,300];
const signed=(n:number)=>`${n>0?"+":""}${n}`;
function clockLabel(offset:number){const total=12*60*60*1000+offset;const day=((total%86400000)+86400000)%86400000;const hh=String(Math.floor(day/3600000)).padStart(2,"0");const mm=String(Math.floor(day%3600000/60000)).padStart(2,"0");const ss=String(Math.floor(day%60000/1000)).padStart(2,"0");const ms=String(day%1000).padStart(3,"0");return `${hh}:${mm}:${ss}.${ms}`;}
export function BerkeleyClockDemo({onBack}:{onBack:()=>void}){
 const [offsets,setOffsets]=useState<number[]>(defaults);
 const [drifts,setDrifts]=useState<number[]>([0,0,0,0,0]);
 const [offline,setOffline]=useState<number[]>([]);
 const [delay,setDelay]=useState(20);
 const [elapsed,setElapsed]=useState(10);
 const [scenario,setScenario]=useState("five-node-average");
 const [run,setRun]=useState<ClockRun|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [auto,setAuto]=useState(false);
 const adjusted=useMemo(()=>offsets.map((o,i)=>Math.round((o+drifts[i]*elapsed)*100)/100),[offsets,drifts,elapsed]);
 const participants=adjusted.map((offset,i)=>({id:i===0?"C0":`N${i}`,name:i===0?"Coordinator C0":`Clock node N${i}`,offset,drift:drifts[i],online:!offline.includes(i)})).filter(n=>n.online);
 const mean=participants.length?Math.round(participants.reduce((s,n)=>s+n.offset,0)/participants.length*100)/100:0;
 const executed=run?run.trace.slice(0,run.current_step):[];
 const current=run&&run.current_step>0?run.trace[run.current_step-1]:null;
 const resultNodes=Array.isArray(run?.result.nodes)?run.result.nodes as Record<string,unknown>[]:[];
 const finalSpread=typeof run?.result.final_spread_ms==="number"?run.result.final_spread_ms:null;
 async function create(){
  setBusy(true);setError("");setNotice("");setAuto(false);
  try{
   const out=await request<{run:ClockRun}>("/experiments",{method:"POST",body:JSON.stringify({lab_id:"physical-clock",scenario,parameters:{offsets,drift_rates_ms_per_s:drifts,simulated_elapsed_s:elapsed,message_delay_ms:delay,unreachable_nodes:offline.map(i=>i===0?"C0":`N${i}`)}})});
   setRun(out.run);setNotice("Experiment persisted. Step through the polling, aggregation and correction phases."); 
  }catch(e){setError(e instanceof Error?e.message:"Unable to create clock experiment");}finally{setBusy(false);}
 }
 async function step(){
  if(!run)return;setBusy(true);setError("");setNotice("");
  try{const out=await request<{run:ClockRun;event:ClockEvent|null}>(`/experiments/${run.id}/step`,{method:"POST"});setRun(out.run);setNotice(out.event?`Step ${out.event.step}: ${out.event.event}`:"All events have been executed.");}
  catch(e){setError(e instanceof Error?e.message:"Step failed");}finally{setBusy(false);}
 }
 async function runAll(){
  if(!run)return;setBusy(true);setError("");setNotice("");setAuto(true);
  try{let active=run;while(active.current_step<active.trace.length){const out=await request<{run:ClockRun;event:ClockEvent|null}>(`/experiments/${active.id}/step`,{method:"POST"});active=out.run;setRun(active);}setNotice("Synchronization round completed. Review the final spread and event ledger.");}
  catch(e){setError(e instanceof Error?e.message:"Run failed");}finally{setBusy(false);setAuto(false);}
 }
 async function reset(){if(!run)return;setBusy(true);setError("");try{const out=await request<{run:ClockRun}>(`/experiments/${run.id}/reset`,{method:"POST"});setRun(out.run);setNotice("Trace cursor reset. Configuration and original result are preserved.");}catch(e){setError(e instanceof Error?e.message:"Reset failed");}finally{setBusy(false);}}
 function exportReport(){const report={exported_at:new Date().toISOString(),run,executed_trace:executed,simulation_only:true};const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download=`aegisgrid-berkeley-clock-run-${run?.id||"draft"}.json`;a.click();URL.revokeObjectURL(url);}
 const finalOffsets=resultNodes.map(n=>Number(n.corrected_offset_ms??n.final_offset_ms??n.offset_ms)).filter(Number.isFinite);
 const spread=finalOffsets.length?Math.max(...finalOffsets)-Math.min(...finalOffsets):null;
 return <div className="advanced-page clock-demo-page">
  <div className="page-intro"><div><div className="eyebrow">DISTRIBUTED SYSTEMS / PHYSICAL TIME</div><h1>Berkeley clock synchronization</h1><p>Run an inspectable synchronization round: poll clock estimates, aggregate participating offsets, send per-node corrections and verify the resulting clock spread.</p></div><div className="intro-actions"><button className="btn-secondary" onClick={onBack}><ChevronLeft size={15}/> All concepts</button><span className="status-pill up"><i/> STEPWISE MODEL</span></div></div>
  <div className="connection-banner connection-demo"><span className="banner-icon"><Clock3 size={17}/></span><div><b>Deterministic clock simulation</b><span>Offsets, drift and network delays are simulated inputs. No host clock is changed and no NTP service is contacted. The coordinator aligns participants to a group estimate, not necessarily UTC.</span></div><span className="banner-mode">SIMULATION</span></div>
  {notice&&<div className="notice"><CheckCircle2 size={16}/><span>{notice}</span></div>}{error&&<div className="connection-banner connection-demo"><AlertTriangle size={17}/><div><b>Experiment error</b><span>{error}</span></div></div>}
  <div className="metric-grid clock-metrics">
   <div className="metric-card"><div className="metric-top"><span>Participating clocks</span><div className="metric-icon tone-blue"><Network size={18}/></div></div><div className="metric-value">{participants.length}<small> / {offsets.length}</small></div><div className="metric-foot"><span>Offline nodes excluded from mean</span></div></div>
   <div className="metric-card"><div className="metric-top"><span>Estimated group offset</span><div className="metric-icon tone-violet"><Activity size={18}/></div></div><div className="metric-value">{signed(mean)}<small> ms</small></div><div className="metric-foot"><span>Preview from current configuration</span></div></div>
   <div className="metric-card"><div className="metric-top"><span>Message delay setting</span><div className="metric-icon tone-orange"><Radio size={18}/></div></div><div className="metric-value">{delay}<small> ms</small></div><div className="metric-foot"><span>Applied as trace timing metadata</span></div></div>
   <div className="metric-card"><div className="metric-top"><span>Round status</span><div className="metric-icon tone-green"><CheckCircle2 size={18}/></div></div><div className="metric-value clock-status-value">{run?run.status.toUpperCase():"READY"}</div><div className="metric-foot"><span>{run?`Run #${run.id} · ${run.current_step}/${run.trace.length} events`:"Configure nodes and create a run"}</span></div></div>
  </div>
  <div className="clock-layout">
   <section className="panel clock-config-panel"><div className="section-head"><div><h3>Experiment configuration</h3><span>Change inputs, then create a new persisted run</span></div><Activity size={17}/></div>
    <label className="advanced-field">Scenario label<input value={scenario} onChange={e=>setScenario(e.target.value)} maxLength={120}/></label>
    <div className="clock-config-heading"><b>Node clock offsets</b><button className="text-link" onClick={()=>{setOffsets(defaults);setDrifts([0,0,0,0,0]);setOffline([]);}}>Reset defaults</button></div>
    <div className="clock-node-configs">{offsets.map((offset,i)=><div className="clock-node-config" key={i}><div className="clock-node-title"><span className={i===0?"clock-node-avatar coordinator":"clock-node-avatar"}>{i===0?"C0":`N${i}`}</span><div><b>{i===0?"Coordinator C0":`Clock node N${i}`}</b><small>{offline.includes(i)?"Excluded from round":i===0?"Coordinator estimate source":"Participating follower"}</small></div><label className="clock-offline-toggle"><input type="checkbox" checked={offline.includes(i)} onChange={e=>setOffline(old=>e.target.checked?[...old,i]:old.filter(n=>n!==i))}/> Offline</label></div>
      <div className="clock-range-row"><label>Initial offset</label><input aria-label={`Node ${i} initial offset`} type="range" min="-500" max="500" step="10" value={offset} onChange={e=>setOffsets(old=>old.map((v,j)=>j===i?Number(e.target.value):v))}/><code>{signed(offset)} ms</code></div>
      <div className="clock-range-row"><label>Drift / second</label><input aria-label={`Node ${i} drift rate`} type="range" min="-5" max="5" step="0.5" value={drifts[i]} onChange={e=>setDrifts(old=>old.map((v,j)=>j===i?Number(e.target.value):v))}/><code>{signed(drifts[i])} ms/s</code></div>
     </div>)}</div>
    <div className="clock-extra-config"><label className="advanced-field">Simulated elapsed time <div className="range-value"><input type="range" min="0" max="60" value={elapsed} onChange={e=>setElapsed(Number(e.target.value))}/><code>{elapsed} s</code></div></label><label className="advanced-field">Message delay <div className="range-value"><input type="range" min="0" max="500" step="10" value={delay} onChange={e=>setDelay(Number(e.target.value))}/><code>{delay} ms</code></div></label></div>
    <div className="experiment-controls clock-controls"><button className="btn-primary" disabled={busy||!scenario.trim()||participants.length===0} onClick={()=>void create()}><Play size={15}/> Create persisted run</button><button className="btn-secondary" disabled={!run||busy||run.current_step>=run.trace.length} onClick={()=>void step()}><StepForward size={15}/> Next event</button><button className="btn-secondary" disabled={!run||busy||run.current_step>=run.trace.length} onClick={()=>void runAll()}><Activity size={15}/>{auto?"Running…":"Run to completion"}</button><button className="btn-secondary" disabled={!run||busy} onClick={()=>void reset()}><RotateCcw size={15}/> Reset trace</button><button className="btn-secondary" disabled={!run} onClick={exportReport}><Download size={15}/> Export JSON</button></div>
    <div className="runtime-caution"><AlertTriangle size={15}/><span>Offline nodes time out and are excluded from the average. Delay is shown as timing metadata in this teaching model; it is not a packet-level network emulator.</span></div>
   </section>
   <section className="panel clock-state-panel"><div className="section-head"><div><h3>Clock state inspection</h3><span>Live preview from configured inputs</span></div><Clock3 size={17}/></div>
    <div className="clock-state-table"><div className="clock-state-head"><span>NODE</span><span>LOCAL CLOCK</span><span>OFFSET</span><span>STATE</span></div>{offsets.map((offset,i)=>{const live= !offline.includes(i);const drifted=offset+drifts[i]*elapsed;const correction=mean-drifted;const final=live?mean:drifted;return <div className="clock-state-row" key={i}><span><b>{i===0?"C0":`N${i}`}</b><small>{i===0?"Coordinator":"Follower"}</small></span><span className="clock-mono">{clockLabel(drifted)}</span><span className={drifted>0?"offset-positive":drifted<0?"offset-negative":""}>{signed(Math.round(drifted*100)/100)} ms</span><span><i className={live?"clock-state-dot online":"clock-state-dot offline"}/>{live?(run&&run.status==="completed"?"Aligned":"Online"):"Offline"}</span><span className="clock-correction-detail">Preview correction: {live?signed(Math.round(correction*100)/100)+" ms":"not applied"} · final estimate {live?signed(final)+" ms":"unchanged"}</span></div>})}</div>
    <div className="clock-chart-block"><div className="section-head"><div><h3>Offset spread</h3><span>Current input offsets vs. ideal group target</span></div></div>{adjusted.map((value,i)=><div className="clock-bar-row" key={i}><span>{i===0?"C0":`N${i}`}</span><div className="clock-bar-track"><i className={value>=0?"positive":"negative"} style={{width:Math.min(100,Math.abs(value)/5)+"%",marginLeft:value<0?Math.max(0,50-Math.abs(value)/10)+"%": "50%"}}/></div><code>{signed(Math.round(value*100)/100)}</code></div>)}<div className="clock-chart-scale"><span>−500 ms</span><span>0 ms</span><span>+500 ms</span></div></div>
    <div className="clock-result-summary"><div><span>Backend mean offset</span><b>{run?String(run.result.mean_offset_ms)+" ms":"Not run"}</b></div><div><span>Final spread</span><b>{finalSpread!==null?finalSpread+" ms":spread!==null&&run?.status==="completed"?spread+" ms":"Pending"}</b></div><div><span>Events executed</span><b>{run?`${run.current_step} / ${run.trace.length}`:"0 / 0"}</b></div></div>
   </section>
  </div>
  <div className="clock-lower-grid">
   <section className="panel feed-panel"><div className="section-head"><div><h3>Berkeley round event ledger</h3><span>{run?`Run #${run.id} · ordered backend trace`:"Create a run to see poll, aggregate and correction events"}</span></div><Activity size={17}/></div><div className="event-feed trace-feed">{run?.trace.map((event,i)=><div className={"feed-row trace-row "+(i<run.current_step?"trace-executed":"")} key={i}><div className={"feed-dot "+(i<run.current_step?"feed-blue":"feed-muted")}/><div className="feed-copy"><b>{String(event.event).replaceAll("."," ")}</b><span>{Object.entries(event).filter(([k])=>k!=="step"&&k!=="event").map(([k,v])=>k+": "+(typeof v==="object"?JSON.stringify(v):String(v))).join(" · ")}</span></div><code>{i<run.current_step?"DONE":"S"+event.step}</code></div>)}{!run&&<div className="empty-state">No events yet. Create an experiment to generate a persisted, inspectable trace.</div>}</div></section>
   <section className="panel runtime-checks"><div className="section-head"><div><h3>Current event detail</h3><span>Payload for the selected execution cursor</span></div><Save size={17}/></div>{current?<><div className="clock-current-event"><span className="clock-event-step">STEP {current.step}</span><h4>{String(current.event).replaceAll("."," ")}</h4><pre>{JSON.stringify(current,null,2)}</pre></div><button className="btn-secondary" onClick={()=>navigator.clipboard?.writeText(JSON.stringify({run,executed_trace:executed},null,2))}><Save size={15}/> Copy run evidence JSON</button></>:<div className="empty-state">Step through the run to inspect the exact event payload, including node, offset, correction and participant decisions.</div>}</section>
  </div>
  <section className="panel clock-math-panel"><div className="section-head"><div><h3>Coordinator calculation audit</h3><span>Values from the backend result, not a hard-coded example</span></div><CheckCircle2 size={17}/></div>{run?<><div className="clock-formula-row"><div><span>Participants included</span><b>{String(run.result.participants??"—")}</b></div><div><span>Arithmetic mean</span><b>{String(run.result.mean_offset_ms??"—")} ms</b></div><div><span>Excluded nodes</span><b>{Array.isArray(run.result.excluded_nodes)?(run.result.excluded_nodes as unknown[]).join(", ")||"None":"—"}</b></div><div><span>Model mode</span><b>{String(run.result.execution_mode??"simulation")}</b></div></div><div className="table-wrap"><table><thead><tr><th>NODE</th><th>INPUT OFFSET</th><th>REPORTED OFFSET</th><th>CORRECTION</th><th>FINAL OFFSET</th><th>STATUS</th></tr></thead><tbody>{resultNodes.map((node,i)=><tr key={String(node.node||i)}><td>{String(node.node||"—")}</td><td>{signed(Number(node.initial_offset_ms??node.offset_ms??0))} ms</td><td>{signed(Number(node.reported_offset_ms??node.offset_ms??0))} ms</td><td>{signed(Number(node.adjustment_ms??0))} ms</td><td>{signed(Number(node.corrected_offset_ms??0))} ms</td><td>{String(node.status??"participating")}</td></tr>)}</tbody></table></div></>:<div className="empty-state">Create a run to inspect the actual calculation output and per-node correction ledger.</div>}</section>
 </div>;
}
