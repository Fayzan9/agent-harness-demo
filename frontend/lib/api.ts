import type { HarnessEvent, Options, RunConfig, WorkspaceFile } from "./types";

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

/** Reads the server-sent event stream from POST /run, one event at a time. */
export async function* streamRun(
  cfg: RunConfig,
  signal: AbortSignal,
): AsyncGenerator<HarnessEvent> {
  const res = await fetch(`${API}/run`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(cfg),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Server returned ${res.status}`);

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
