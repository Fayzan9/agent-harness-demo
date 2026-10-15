import { clearToken, getToken, SIGNED_OUT } from "./auth";
import type {
  EvalOptions,
  EvalStream,
  HarnessEvent,
  Options,
  RunConfig,
  SessionDetail,
  SessionSummary,
  WorkspaceFile,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const JSON_HEADERS = { "Content-Type": "application/json" };

/** fetch that adds the sign-in token, and tells the app when the server stops accepting it. */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = { ...(init.headers as Record<string, string>), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new Event(SIGNED_OUT));
  }
  return res;
}

export type AuthConfig = { mode: "off" | "jwt"; client_id: string };
export type Me = { id: string; email: string };

export const getAuthConfig = (): Promise<AuthConfig> => fetch(`${API}/auth/config`).then((r) => r.json());

/** Who the server thinks we are. 403 means signed in but not on the allowlist. */
export const getMe = async (): Promise<{ me?: Me; status: number }> => {
  const res = await apiFetch("/auth/me");
  return { status: res.status, me: res.ok ? await res.json() : undefined };
};

export const getOptions = (): Promise<Options> =>
  apiFetch("/options").then((r) => r.json());

export const getWorkspace = (): Promise<WorkspaceFile[]> =>
  apiFetch("/workspace").then((r) => r.json());

export const resetWorkspace = () => apiFetch("/workspace/reset", { method: "POST" });

export const approve = (call_id: string, allow: boolean) =>
  apiFetch("/approve", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ call_id, allow }),
  });

export const compact = (run_id: string) =>
  apiFetch("/compact", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ run_id }),
  });

export const getSessions = (): Promise<SessionSummary[]> => apiFetch("/sessions").then((r) => r.json());

export const getSession = (id: string): Promise<SessionDetail> => apiFetch(`/sessions/${id}`).then((r) => r.json());

/** Reads the server-sent event stream from a POST endpoint, one event at a time. */
async function* streamPost<T = HarnessEvent>(path: string, body: unknown, signal: AbortSignal): AsyncGenerator<T> {
  const res = await apiFetch(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body), signal });
  if (!res.ok || !res.body) {
    const detail = await res.json().then((d) => d.detail).catch(() => undefined);
    throw new Error(detail ?? `Server returned ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      if (chunk.startsWith("data: ")) yield JSON.parse(chunk.slice(6));
    }
  }
}

/** A new chat, or the next message of an existing one. */
export const streamRun = (cfg: RunConfig, sessionId: string | null, signal: AbortSignal) =>
  streamPost("/run", { ...cfg, session_id: sessionId }, signal);

export const streamResume = (sessionId: string, cfg: RunConfig, signal: AbortSignal) =>
  streamPost(`/sessions/${sessionId}/resume`, cfg, signal);

export const streamBranch = (runId: string, eventIndex: number, cfg: RunConfig, signal: AbortSignal) =>
  streamPost("/branch", { ...cfg, run_id: runId, event_index: eventIndex }, signal);

export const getEvalOptions = (): Promise<EvalOptions> => apiFetch("/evals/options").then((r) => r.json());

export const streamEvals = (body: { cases: string[]; variants: string[]; runs: number }, signal: AbortSignal) =>
  streamPost<EvalStream>("/evals/run", body, signal);
