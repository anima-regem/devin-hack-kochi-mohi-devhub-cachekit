export type Finding = {
  id: string; route: string; breaker: string; severity: "high" | "medium" | "low";
  first_divergence_token: number; stable_tokens_after: number; requests_affected: number;
  tokens_wasted: number; safe_to_move: boolean; evidence: string[]; fix_hint: string;
};
export type Backend = {
  backend: string; actual_hit_rate: number; achievable_hit_rate: number;
  tokens_recomputed_actual: number; tokens_recomputed_achievable: number;
  cost_actual: number | null; cost_achievable: number | null;
  params: { model?: string; block_size?: number; heatmap_reference_tokens?: Record<string, number>; limitations?: string[] };
};
export type ReportBundle = {
  id: string;
  report: { version: string; n_requests: number; routes: string[]; backends: Backend[];
    findings: Finding[]; heatmaps: Record<string, number[]>; template_preview: Record<string, string>;
    input_sha256: string; config_sha256: string; };
  metadata: { timestamp: string; git_sha: string | null; git_dirty?: boolean | null; model: string;
    dataset: string[]; gpu: null; vllm_version: string; report_sha256: string; seed: Record<string, number[]>;
    tokenizer: { revision: string }; note: string; };
};
export type Verification = {
  passed: boolean; task_id: string; diff_sha256: string; hit_rate_before: number;
  hit_rate_after: number | null; content_check: { passed: boolean; missing_lines: number;
    unexpected_added_lines: number; tools_equal: boolean; } | null;
  scope_check: { passed: boolean }; signature_check: { passed: boolean };
  tests: { status: string }; prefix_check: { passed: boolean };
  quality_guard: { status: string; reason: string; cases: { id: string; exact_match: boolean;
    before_assertions: Record<string, boolean>; after_assertions: Record<string, boolean>;
    json_before_valid: boolean | null; json_after_valid: boolean | null; reviewed: boolean; truncated: boolean }[] };
};
export type TaskView = {
  task: { id: string; allowed_files: string[]; target_hit_rate: number; [key: string]: unknown };
  markdown: string; state: "prepared" | "candidate" | "stale";
  verification: Verification | null; verification_current: boolean;
  handoff: { status: string; pr_url: string | null; session_url: string | null } | null;
  golden_cases: { id: string; category: string; assertions: string[]; expects_json: boolean }[];
  note: string;
};
export type BenchView = {
  smoke: { status: string; model: string; revision: string; gpu: string; vllm_version: string;
    timestamp: string; block_size: number; capacity_tokens: number; source: string; sha256: string;
    requests: { request: number; prompt_tokens: number; cached_tokens: number; queried_tokens: number }[] } | null;
  benchmarks: Record<string, unknown>[]; note: string;
};
export type Demo = { report: ReportBundle; fix: TaskView | null; bench: BenchView };
export type Loaded<T> = { data: T; source: "API" | "SAVED" };
export type Dataset = { id: string; name: string; available: boolean; description: string };

const configured = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
export function apiBase() {
  const url = new URL(configured);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  const modal = url.protocol === "https:" && url.hostname.endsWith(".modal.run");
  if (!["http:", "https:"].includes(url.protocol) || (!local && !modal) || url.username || url.password || url.search || url.hash) {
    throw new Error("Connect a local API or your Modal endpoint to work with logs.");
  }
  return configured.replace(/\/$/, "");
}
export async function api<T>(path: string, options: RequestInit = {}, timeout = 1500): Promise<T> {
  const response = await fetch(apiBase() + path, { ...options, signal: AbortSignal.timeout(timeout) });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "The local API could not complete this request.");
  }
  return response.json();
}
export async function demo(): Promise<Demo> {
  const response = await fetch("/demo/workspace.json");
  if (!response.ok) throw new Error("Saved demo is unavailable. Export the synthetic demo and reload.");
  return response.json();
}
export async function report(id: string): Promise<Loaded<ReportBundle>> {
  try { return { data: await api<ReportBundle>(`/reports/${encodeURIComponent(id)}/bundle`), source: "API" }; }
  catch {
    const saved = await demo();
    if (saved.report.id !== id) throw new Error("This report needs your local API. Reconnect it, or open the saved helpdesk report.");
    return { data: saved.report, source: "SAVED" };
  }
}
export async function fix(id?: string): Promise<Loaded<TaskView>> {
  const saved = await demo();
  const key = id || saved.fix?.task.id;
  if (!key) throw new Error("No fix task is available. Generate one from a report.");
  try { return { data: await api<TaskView>(`/fix/${encodeURIComponent(key)}`), source: "API" }; }
  catch {
    if (!saved.fix || saved.fix.task.id !== key) throw new Error("This task needs your local API. Reconnect to inspect its current source and evidence.");
    return { data: saved.fix, source: "SAVED" };
  }
}
export const percent = (n: number) => new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 2 }).format(n);
export const number = (n: number) => new Intl.NumberFormat("en").format(n);
export const words = (text: string) => text.replaceAll("_", " ");
