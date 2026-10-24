"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, demo, fix, report, number, percent, words, type BenchView, type Dataset,
  type Finding, type Loaded, type ReportBundle, type TaskView, type Verification } from "@/lib/workspace";

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function ErrorState({ message }: { message: string }) {
  return <section className="notice error" role="alert"><h2>Could not load this workspace</h2><p>{message}</p><Link href="/report/demo-before">Open the saved report</Link></section>;
}
function Loading() { return <p className="loading" role="status">Loading saved evidence…</p>; }
function Metadata({ data }: { data: ReportBundle }) {
  return <details className="metadata"><summary>Run provenance</summary><dl>
    <div><dt>Saved</dt><dd>{data.metadata.timestamp}</dd></div>
    <div><dt>Model</dt><dd>{data.metadata.model}</dd></div>
    <div><dt>Tokenizer revision</dt><dd><code>{data.metadata.tokenizer.revision}</code></dd></div>
    <div><dt>Git revision</dt><dd>{data.metadata.git_sha || "Unrecorded · pre-Git run"}{data.metadata.git_dirty ? " · working tree had changes" : ""}</dd></div>
    <div><dt>Input SHA-256</dt><dd><code>{data.report.input_sha256}</code></dd></div>
    <div><dt>Configuration SHA-256</dt><dd><code>{data.report.config_sha256}</code></dd></div>
    <div><dt>Evidence</dt><dd>{data.metadata.note}</dd></div>
  </dl></details>;
}
function useReport(id: string) {
  const [state, setState] = useState<{ loaded?: Loaded<ReportBundle>; error?: string }>({});
  useEffect(() => { let active = true; report(id).then(loaded => { if (active) setState({ loaded }); })
    .catch(error => { if (active) setState({ error: error.message }); }); return () => { active = false; }; }, [id]);
  return state;
}
function Reuse({ data }: { data: ReportBundle }) {
  const profile = data.report.backends.find(b => b.backend === "vllm");
  if (!profile) return <p>No vLLM result is available.</p>;
  return <section className="reuse" aria-labelledby="reuse-title">
    <div className="section-heading"><h2 id="reuse-title">A longer reusable prefix</h2><Badge>SIMULATED</Badge></div>
    <div className="reuse-row"><span>Current reuse</span><div className="bar-track"><span style={{ width: `${profile.actual_hit_rate * 100}%` }} /></div><strong>{percent(profile.actual_hit_rate)}</strong></div>
    <div className="reuse-row projected"><span>Projected reuse</span><div className="bar-track"><span style={{ width: `${profile.achievable_hit_rate * 100}%` }} /></div><strong>{percent(profile.achievable_hit_rate)}</strong></div>
    <p className="supporting-text">Projection reorders eligible content. It is not a measured speedup or an approved application fix.</p>
  </section>;
}

export function AnalyzeWorkspace() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [connected, setConnected] = useState(false);
  const [saved, setSaved] = useState<ReportBundle>();
  const [selected, setSelected] = useState("demo-before");
  const [file, setFile] = useState<File>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Dataset[]>("/datasets").then(data => { if (active) { setDatasets(data); setConnected(true); } }).catch(() => {});
    demo().then(data => { if (active) setSaved(data.report); }).catch(() => {});
    return () => { active = false; };
  }, []);
  async function analyze(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = file
        ? await api<{ report_id: string }>("/analyze/upload", { method: "POST", body: file, headers: { "Content-Type": "application/x-ndjson" } }, 120000)
        : await api<{ report_id: string }>("/analyze", { method: "POST", body: JSON.stringify({ dataset_id: selected }), headers: { "Content-Type": "application/json" } }, 120000);
      router.push(`/report/${result.report_id}`);
    } catch (error) { setError(error instanceof Error ? error.message : "Analysis could not finish."); setBusy(false); }
  }
  return <>
    <section className="page-intro"><h1>Find where reuse stops.</h1><p className="lede">See which changing details interrupt a shared prompt, then give your coding agent a fix it can verify.</p></section>
    <div className="analyze-grid"><section className="input-panel"><div className="section-heading"><h2>Analyze a request log</h2><Badge tone={connected ? "good" : "neutral"}>{connected ? "LOCAL API" : "SAVED DEMO"}</Badge></div>
      <form onSubmit={analyze}><label htmlFor="dataset">Local dataset</label><select id="dataset" value={selected} onChange={e => { setSelected(e.target.value); setFile(undefined); }} disabled={!connected || busy}>
        {datasets.length ? datasets.map(d => <option key={d.id} value={d.id} disabled={!d.available}>{d.name}{d.available ? "" : " · unavailable"}</option>) : <option value="demo-before">Fictional helpdesk · BEFORE</option>}
      </select><label htmlFor="upload">Or choose your JSONL file</label><input id="upload" type="file" accept=".jsonl,.ndjson" disabled={!connected || busy} onChange={e => setFile(e.target.files?.[0])} />
      <p className="supporting-text">Logs stay on your local API or your Modal workspace. No inference runs during analysis.</p>
      <label htmlFor="profile">Cache profile</label><input id="profile" readOnly value="vLLM · pinned Qwen tokenizer" />
      <button className="button primary" disabled={!connected || busy} type="submit">{busy ? "Analyzing locally…" : "Analyze log"}</button>
      {!connected && <p className="supporting-text">Start the local API to analyze files. The saved report works without it.</p>}
      {error && <p className="notice error" role="alert">{error}</p>}</form>
    </section><section className="saved-panel"><h2>Explore the helpdesk run</h2><p>A fictional support agent mixes changing context into its reusable instructions. Inspect the actual saved findings.</p>
      {saved && <><p className="run-line"><strong>{number(saved.report.n_requests)}</strong> requests <span aria-hidden="true">·</span> <strong>{number(saved.report.findings.length)}</strong> findings <Badge>SAVED</Badge></p><Reuse data={saved} /></>}
      <Link className="button" href="/report/demo-before">Open saved report <span aria-hidden="true">→</span></Link>
    </section></div>
    <section className="workflow-note"><h2>Evidence before approval</h2><p>Analysis produces a scoped refactoring task. Verification checks preserved content, repository tests and golden outputs. Missing or failed quality evidence leaves the change unapproved.</p><Link href="/how-it-works">Read the method and limitations</Link></section>
  </>;
}

function FindingRow({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false);
  return <><tr><td><button className="finding-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{words(finding.breaker)} <span aria-hidden="true">{expanded ? "−" : "+"}</span></button></td>
    <td><Badge tone={finding.severity === "high" ? "warn" : "neutral"}>{finding.severity}</Badge></td><td>{number(finding.requests_affected)}</td><td>{number(finding.stable_tokens_after)}</td><td>{finding.safe_to_move ? "Eligible for projection" : "Review required"}</td></tr>
    {expanded && <tr><td colSpan={5} className="finding-detail"><p>{finding.fix_hint}</p><dl className="inline-data"><div><dt>First observed divergence</dt><dd>Token {number(finding.first_divergence_token)}</dd></div><div><dt>Potential stable-token recomputation</dt><dd>{number(finding.tokens_wasted)} · overlapping attribution</dd></div></dl>{finding.evidence.map((text, i) => <p className="evidence" key={i}>{text}</p>)}<p className="supporting-text">Exact source locations are pending the source-locator enhancement.</p></td></tr>}
  </>;
}

export function ReportWorkspace({ id }: { id: string }) {
  const { loaded, error } = useReport(id);
  const router = useRouter();
  const [busy, setBusy] = useState(false); const [taskError, setTaskError] = useState("");
  if (error) return <ErrorState message={error} />;
  if (!loaded) return <Loading />;
  const { data, source } = loaded;
  const backend = data.report.backends.find(b => b.backend === "vllm");
  async function createTask() {
    setBusy(true); setTaskError("");
    try { const task = await api<TaskView>(`/reports/${encodeURIComponent(id)}/task`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, 120000); router.push(`/fix/${task.task.id}`); }
    catch (error) { setTaskError(error instanceof Error ? error.message : "The task could not be prepared."); setBusy(false); }
  }
  return <><Link href="/" className="back-link">← Workspace</Link><header className="report-header"><div><h1>Prompt reuse, explained.</h1><p className="lede">{data.report.routes.join(" · ")}</p></div><div className="badges"><Badge>{source}</Badge><Badge>SIMULATED</Badge></div></header>
    <div className="run-facts"><div><span>Requests</span><strong>{number(data.report.n_requests)}</strong></div><div><span>Routes</span><strong>{number(data.report.routes.length)}</strong></div><div><span>Findings</span><strong>{number(data.report.findings.length)}</strong></div><div><span>Profile</span><strong>vLLM</strong></div></div>
    <Reuse data={data} />
    {backend && <div className="recomputed"><p><span>Tokens recomputed · current</span><strong>{number(backend.tokens_recomputed_actual)}</strong></p><p><span>Tokens recomputed · projection</span><strong>{number(backend.tokens_recomputed_achievable)}</strong></p><p><span>Serving cost</span><strong className="pending">&lt;pending&gt;</strong></p></div>}
    <section className="report-section"><div className="section-heading"><h2>Follow a route</h2><span className="supporting-text">Inspect the prompt and aligned stability</span></div><div className="route-list">{data.report.routes.map(route => <Link key={route} href={`/report/${encodeURIComponent(id)}/heatmap/${encodeURIComponent(route)}`}><code>{route}</code><span>Open heatmap →</span></Link>)}</div></section>
    <section className="report-section"><h2>Findings</h2><p className="supporting-text">Ordered by potential recomputation. Estimates overlap and cannot be added as causal savings.</p><div className="table-scroll"><table><caption className="sr-only">Detected cache breakers and simulated downstream impact</caption><thead><tr><th>Breaker</th><th>Severity</th><th>Requests</th><th>Stable tokens after</th><th>Movement</th></tr></thead><tbody>{data.report.findings.map(f => <FindingRow key={f.id} finding={f} />)}</tbody></table></div>{!data.report.findings.length && <p className="notice">No breakers were detected in this run. Sampling and heuristics can miss variants.</p>}</section>
    <section className="action-panel"><div><h2>Turn findings into a fix task</h2><p>Export redacted requirements, preserve the recorded baseline, and verify the resulting code change.</p></div><div className="actions"><button className="button primary" onClick={createTask} disabled={source !== "API" || busy}>{busy ? "Preparing baseline…" : "Generate fix task"}</button><Link className="button" href="/fix">Saved fix status</Link></div>{source === "SAVED" && <p className="supporting-text">Task generation needs the local API and recorded helpdesk inputs.</p>}{taskError && <p role="alert" className="notice error">{taskError}</p>}</section>
    <Metadata data={data} />
  </>;
}

export function HeatmapWorkspace({ id, route }: { id: string; route: string }) {
  const { loaded, error } = useReport(id); const [full, setFull] = useState(false);
  if (error) return <ErrorState message={error} />;
  if (!loaded) return <Loading />;
  const { data, source } = loaded; const values = data.report.heatmaps[route];
  if (!values) return <ErrorState message="This route is not part of the saved report." />;
  const findings = data.report.findings.filter(f => f.route === route);
  const first = findings.length ? Math.min(...findings.map(f => f.first_divergence_token)) : null;
  const total = data.report.backends[0]?.params.heatmap_reference_tokens?.[route];
  const marker = first !== null && total ? Math.min(values.length, first / total * values.length) : null;
  const preview = data.report.template_preview[route] || "";
  const text = full ? preview : preview.slice(0, 12000);
  return <><Link className="back-link" href={`/report/${id}`}>← Report</Link><header className="report-header"><div><h1>Where the prefix breaks.</h1><p className="lede"><code>{route}</code></p></div><div className="badges"><Badge>{source}</Badge><Badge>SIMULATED</Badge></div></header>
    <div className="heatmap-toolbar"><div className="segmented"><button aria-pressed="true">BEFORE</button><button disabled title="A current approved fix is required">AFTER · pending</button></div><div className="legend"><span className="legend-stable" />Stable<span className="legend-variable" />Variable</div></div>
    <section className="heatmap-panel"><h2>Aligned token stability</h2><svg className="stability-strip" viewBox={`0 0 ${values.length || 1} 56`} preserveAspectRatio="none" role="img" aria-label="Downsampled stability along the reference prompt; green is shared static content and red is changing content">
      {values.map((value, i) => <rect key={i} x={i} y="12" width="1.1" height="32" fill={value === 1 ? "var(--stable)" : `rgb(${160 - value * 70} ${66 + value * 60} ${54 + value * 35})`} />)}
      {marker !== null && <line x1={marker} x2={marker} y1="0" y2="56" stroke="var(--ink)" strokeWidth={Math.max(values.length / 600, 1)} />}
    </svg><p>{first === null ? "No divergence finding is available for this route." : <>Earliest observed divergence: <strong>token {number(first)}</strong>.</>} {total ? <>Reference prompt: {number(total)} tokens.</> : "Exact reference length is not recorded in this older run."}</p><p className="supporting-text">The strip is downsampled. Stable content after a changing prefix can still require recomputation; green does not mean a measured cache hit.</p></section>
    <section className="report-section"><h2>Redacted prompt template</h2><p className="supporting-text">Variable spans are marked. This text view is aligned structurally; its character positions are not token offsets.</p><pre className="prompt-view">{text.split(/(⟦[^⟧]*⟧)/g).map((part, i) => part.startsWith("⟦") ? <mark key={i}>{words(part)}</mark> : <span key={i}>{part}</span>)}</pre>{preview.length > 12000 && <button className="text-button" onClick={() => setFull(!full)}>{full ? "Collapse template" : "Show full redacted template"}</button>}</section><Metadata data={data} />
  </>;
}

export function FixWorkspace({ id }: { id?: string }) {
  const [loaded, setLoaded] = useState<Loaded<TaskView>>(); const [error, setError] = useState("");
  const [busy, setBusy] = useState(false); const [verificationId, setVerificationId] = useState("");
  const [qualityId, setQualityId] = useState(""); const [reviews, setReviews] = useState("");
  const [reviewer, setReviewer] = useState(""); const [confirmation, setConfirmation] = useState(""); const [approved, setApproved] = useState(false);
  useEffect(() => { let active = true; fix(id).then(data => { if (active) setLoaded(data); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [id]);
  if (!loaded) return error ? <ErrorState message={error} /> : <Loading />;
  const view = loaded.data; const v = view.verification;
  const canApprove = loaded.source === "API" && view.verification_current && v?.passed && v.quality_guard.status === "passed" && !!verificationId;
  async function verify() { if (!loaded) return; setBusy(true); setError(""); try {
    const response = await api<{ id: string; result: Verification }>("/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task_id: loaded.data.task.id, quality_run_id: qualityId.trim() || null, review_ids: reviews.trim().split(/\s+/).filter(Boolean) }) }, 180000);
    setVerificationId(response.id); setApproved(false);
    const current = await api<TaskView>(`/fix/${loaded.data.task.id}`, {}, 15000);
    setLoaded({ source: "API", data: current });
  } catch (e) { setError(e instanceof Error ? e.message : "Verification failed."); } finally { setBusy(false); } }
  async function approve() { if (!loaded || !v) return; setBusy(true); setError(""); try {
    await api("/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task_id: view.task.id, verification_id: verificationId, diff_sha256: confirmation, reviewer, review_ids: reviews.trim().split(/\s+/).filter(Boolean) }) }, 180000); setApproved(true);
  } catch (e) { setError(e instanceof Error ? e.message : "Approval failed."); } finally { setBusy(false); } }
  function download() { const url = URL.createObjectURL(new Blob([view.markdown], { type: "text/markdown" })); const a = document.createElement("a"); a.href = url; a.download = "fix_task.md"; a.click(); URL.revokeObjectURL(url); }
  return <><Link href="/report/demo-before" className="back-link">← Report</Link><header className="report-header"><div><h1>Verify the change.</h1><p className="lede">A scoped task, preserved inputs and evidence tied to the exact source.</p></div><div className="badges"><Badge>{loaded.source}</Badge><Badge tone="warn">{approved ? "APPROVAL RECORDED" : "NOT APPROVED"}</Badge></div></header>
    <section className="notice"><h2>{view.state === "stale" ? "This saved task predates the current source." : view.state === "candidate" ? "A candidate change is ready to check." : "The task is prepared; a code change is still needed."}</h2><p>{view.state === "stale" ? "Generate a fresh task from the report before using it for a real fix. Historical checks below do not approve today's source." : view.note}</p></section>
    <section className="report-section"><div className="section-heading"><h2>Fixer handoff</h2><Badge>{view.handoff?.status || "NOT STARTED"}</Badge></div><p>Use the redacted task with your coding agent. A real Devin session needs Mohith’s explicit approval and a quota cap.</p>{view.handoff?.pr_url && <a href={view.handoff.pr_url}>Open the fix PR</a>}<div className="actions"><button className="button" onClick={download}>Download redacted task</button><button className="button primary" onClick={verify} disabled={loaded.source !== "API" || busy || view.state === "stale"}>{busy ? "Checking…" : "Run local verification"}</button></div><details className="task-document"><summary>Read the fix task</summary><pre>{view.markdown}</pre></details></section>
    <details className="metadata"><summary>Attach saved behavioral evidence</summary><p>Run the explicit quality collector on your local or Modal inference endpoint first. Enter file SHA-256 identities from eval_results/quality_guard/. Verification reads existing evidence; it never starts inference.</p><label htmlFor="quality-id">Quality run SHA-256 (optional)</label><input id="quality-id" value={qualityId} onChange={e => { setQualityId(e.target.value); setVerificationId(""); }} disabled={loaded.source !== "API" || busy} spellCheck={false} /><label htmlFor="review-ids">Review artifact SHA-256 identities (space separated)</label><input id="review-ids" value={reviews} onChange={e => { setReviews(e.target.value); setVerificationId(""); }} disabled={loaded.source !== "API" || busy} spellCheck={false} /><p className="supporting-text">Changed outputs require an explicit artifact-bound review. Missing evidence leaves the quality gate NOT RUN.</p></details>
    <section className="report-section"><h2>Verification gates</h2>{!view.verification_current && <p className="supporting-text">Saved results are historical. Current evidence is required before approval.</p>}<div className="gate-list">{[
      ["Content preserved", v?.content_check?.passed], ["Allowed source scope", v?.scope_check.passed], ["Public signature", v?.signature_check.passed], ["Reuse target", v?.prefix_check.passed], ["Repository tests", v ? v.tests.status === "passed" : undefined],
    ].map(([label, passed]) => <div key={String(label)}><span>{label}</span><Badge tone={view.verification_current && passed ? "good" : "neutral"}>{passed === undefined ? "PENDING" : !view.verification_current ? "HISTORICAL" : passed ? "PASS" : "NOT PASSED"}</Badge></div>)}</div></section>
    <section className="report-section"><div className="section-heading"><h2>Behavioral quality guard</h2><Badge tone="warn">{words(v?.quality_guard.status || "not_run")}</Badge></div><p>{v?.quality_guard.reason || "No actual golden inference evidence has been collected."}</p><div className="golden-list">{view.golden_cases.map(c => { const result = v?.quality_guard.cases.find(r => r.id === c.id); return <article className="golden-case" key={c.id}><div className="section-heading"><h3>{words(c.category)}</h3><Badge>{!result ? "NOT RUN" : !view.verification_current ? "HISTORICAL" : Object.values(result.after_assertions).every(Boolean) ? "ASSERTIONS PASS" : "ASSERTION FAILED"}</Badge></div><p className="supporting-text">{c.assertions.map(a => a.replaceAll("-", " ")).join(" · ")}</p>{result && <p className="supporting-text">{result.exact_match ? "Exact output match" : result.reviewed ? "Changed output reviewed" : "Output changed · review required"} · JSON {result.json_after_valid === null ? "not applicable" : result.json_after_valid ? "valid" : "invalid"}</p>}</article>; })}</div><p className="supporting-text">A small passing suite supports its tested cases. It does not establish universal equivalence.</p></section>
    <section className="action-panel"><h2>Approve the exact verified diff</h2><p>{canApprove ? "Review the changes, enter your name and confirm the complete diff hash." : "Approval stays unavailable until current verification and behavioral evidence pass."}</p><code className="hash">{v?.diff_sha256 || "<pending>"}</code><label htmlFor="reviewer">Reviewer name</label><input id="reviewer" disabled={!canApprove || busy} value={reviewer} onChange={e => setReviewer(e.target.value)} /><label htmlFor="diff-confirm">Confirm diff SHA-256</label><input id="diff-confirm" disabled={!canApprove || busy} value={confirmation} onChange={e => setConfirmation(e.target.value)} /><button className="button primary" disabled={!canApprove || busy || !reviewer.trim() || confirmation !== v?.diff_sha256 || approved} onClick={approve}>{approved ? "Approval recorded" : "Record approval"}</button><p className="supporting-text">Recording approval does not merge the PR.</p></section>{error && <p className="notice error" role="alert">{error}</p>}
  </>;
}

export function BenchWorkspace() {
  const [loaded, setLoaded] = useState<Loaded<BenchView>>(); const [error, setError] = useState("");
  useEffect(() => { let active = true; api<BenchView>("/bench").then(data => ({ data, source: "API" as const })).catch(async () => ({ data: (await demo()).bench, source: "SAVED" as const })).then(data => { if (active) setLoaded(data); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, []);
  if (error) return <ErrorState message={error} />;
  if (!loaded) return <Loading />;
  const smoke = loaded.data.smoke;
  return <><header className="report-header"><div><h1>Measured evidence.</h1><p className="lede">Keep serving validation separate from performance claims.</p></div><Badge>{loaded.source}</Badge></header><section className="notice"><h2>BEFORE / AFTER benchmark pending</h2><p>{loaded.data.note} TTFT, GPU time and dollar savings have not been established.</p></section>{smoke && <section className="report-section"><div className="section-heading"><h2>Prefix-cache smoke test</h2><Badge>MEASURED · SMOKE</Badge></div><p>{smoke.model} · {smoke.gpu} · vLLM {smoke.vllm_version}</p><div className="table-scroll"><table><caption>Observed token-counter changes after each synthetic request</caption><thead><tr><th>Request</th><th>Prompt tokens</th><th>Cache hits</th><th>Cache queries</th></tr></thead><tbody>{smoke.requests.map(r => <tr key={r.request}><td>{number(r.request)}</td><td>{number(r.prompt_tokens)}</td><td>{number(r.cached_tokens)}</td><td>{number(r.queried_tokens)}</td></tr>)}</tbody></table></div><p className="supporting-text">Counters count tokens; only whole blocks are reused. Profile: {number(smoke.block_size)} tokens per block, {number(smoke.capacity_tokens)} KV tokens. These are smoke-test observations, not a BEFORE/AFTER benchmark.</p><details className="metadata"><summary>Smoke run provenance</summary><dl><div><dt>Recorded</dt><dd>{smoke.timestamp}</dd></div><div><dt>Model revision</dt><dd><code>{smoke.revision}</code></dd></div><div><dt>Saved source</dt><dd><code>{smoke.source}</code></dd></div><div><dt>Artifact SHA-256</dt><dd><code>{smoke.sha256}</code></dd></div></dl></details></section>}<section className="report-section"><h2>What the performance replay must establish</h2><ul className="plain-list"><li>Cache reuse and time to first token on the same BEFORE / AFTER traffic.</li><li>Agreement between the simulator and server token counters.</li><li>Serving cost from measured GPU allocation and configured pricing.</li><li>A current quality pass before an application fix is approved.</li></ul></section></>;
}
