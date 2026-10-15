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

export const getOptions = (): Promise<Options> =>
  fetch(`${API}/options`).then((r) => r.json());

export const getWorkspace = (): Promise<WorkspaceFile[]> =>
  fetch(`${API}/workspace`).then((r) => r.json());

export const resetWorkspace = () => fetch(`${API}/workspace/reset`, { method: "POST" });

export const approve = (call_id: string, allow: boolean) =>
  fetch(`${API}/approve`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ call_id, allow }),
  });

export const compact = (run_id: string) =>
  fetch(`${API}/compact`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ run_id }),
  });

export const getSessions = (): Promise<SessionSummary[]> => fetch(`${API}/sessions`).then((r) => r.json());

export const getSession = (id: string): Promise<SessionDetail> => fetch(`${API}/sessions/${id}`).then((r) => r.json());

/** Reads the server-sent event stream from a POST endpoint, one event at a time. */
async function* streamPost<T = HarnessEvent>(path: string, body: unknown, signal: AbortSignal): AsyncGenerator<T> {
  const res = await fetch(`${API}${path}`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body), signal });
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

export const getEvalOptions = (): Promise<EvalOptions> => fetch(`${API}/evals/options`).then((r) => r.json());

export const streamEvals = (body: { cases: string[]; variants: string[]; runs: number }, signal: AbortSignal) =>
  streamPost<EvalStream>("/evals/run", body, signal);
