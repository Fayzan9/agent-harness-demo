import type { HarnessEvent } from "./types";

export type SpanKind = "model" | "tool" | "helper" | "wait" | "compaction" | "tick";

export type Span = {
  id: string;
  label: string;
  kind: SpanKind;
  start: number; // seconds since the run began
  end: number;
  depth: number; // 1 for anything a helper agent did
  lines: string[];
  ongoing?: boolean;
};

export type TraceStats = {
  modelTime: number;
  toolTime: number;
  waitYou: number;
  waitRetry: number;
  promptTokens: number;
  completionTokens: number;
  cachedTokens: number;
  modelCalls: number;
};

export type Trace = { spans: Span[]; total: number; stats: TraceStats };

const short = (s: unknown, n = 140) => {
  const t = String(s ?? "");
  return t.length > n ? `${t.slice(0, n)}...` : t;
};

/**
 * Turns the event list into timed spans. Events are stamped when they are created, which is the end of
 * the work they describe, so a span starts at its event time minus its recorded duration.
 */
export function buildTrace(events: HarnessEvent[]): Trace {
  const stats: TraceStats = {
    modelTime: 0,
    toolTime: 0,
    waitYou: 0,
    waitRetry: 0,
    promptTokens: 0,
    completionTokens: 0,
    cachedTokens: 0,
    modelCalls: 0,
  };
  if (!events.length) return { spans: [], total: 0, stats };

  const t0 = events[0].ts;
  const tEnd = events[events.length - 1].ts;
  const rel = (t: number) => Math.max(0, t - t0);

  const calls = new Map<string, { name: string; args: unknown }>();
  const results = new Map<string, HarnessEvent>();
  const tasks = new Map<string, string>();
  for (const e of events) {
    if (e.type === "model_replied") for (const c of e.data.tool_calls) calls.set(c.id, c);
    if (e.type === "tool_result") results.set(e.data.call_id, e);
    if (e.type === "subagent_started") tasks.set(e.agent, e.data.task);
  }

  const spans: Span[] = [];
  const modelCount: Record<string, number> = {};
  const add = (s: Omit<Span, "depth">, e: HarnessEvent) => spans.push({ ...s, depth: e.agent === "main" ? 0 : 1 });

  events.forEach((e, i) => {
    const d = e.data;
    const id = `${e.type}-${i}`;

    if (e.type === "model_replied") {
      modelCount[e.agent] = (modelCount[e.agent] ?? 0) + 1;
      const u = d.usage ?? { prompt: 0, completion: 0, cached: 0 };
      stats.modelTime += d.duration;
      stats.modelCalls += 1;
      stats.promptTokens += u.prompt;
      stats.completionTokens += u.completion;
      stats.cachedTokens += u.cached;
      const asked = d.tool_calls.map((c: { name: string; args: unknown; error?: string }) =>
        c.error ? `${c.name} with broken arguments` : `${c.name}(${short(JSON.stringify(c.args), 60)})`,
      );
      add(
        {
          id,
          label: `${e.agent === "main" ? "Model call" : "Helper model call"} ${modelCount[e.agent]}`,
          kind: "model",
          start: rel(e.ts - d.duration),
          end: rel(e.ts),
          lines: [
            `Sent ${u.prompt} tokens, got ${u.completion} back.`,
            `Served from the provider's cache: ${u.cached} tokens.`,
            asked.length ? `Asked to use ${asked.join(", ")}.` : `Replied: ${short(d.text)}`,
          ],
        },
        e,
      );
    }

    if (e.type === "tool_result") {
      const call = calls.get(d.call_id);
      const args = call ? short(JSON.stringify(call.args), 100) : "";
      if (!d.allowed) {
        add({ id, label: `${d.tool} not run`, kind: "tick", start: rel(e.ts), end: rel(e.ts), lines: [short(d.result)] }, e);
        return;
      }
      const isHelper = d.tool === "delegate";
      if (!isHelper) stats.toolTime += d.duration;
      add(
        {
          id,
          label: isHelper ? "Helper agent" : `Tool: ${d.tool}`,
          kind: isHelper ? "helper" : "tool",
          start: rel(e.ts - d.duration),
          end: rel(e.ts),
          lines: isHelper
            ? [`Task: ${short(call && (call.args as { task?: string }).task)}`, "Everything the helper did is nested below.", `Returned: ${short(d.result)}`]
            : [`Arguments: ${args}`, `Result: ${short(d.result)}`],
        },
        e,
      );
    }

    if (e.type === "approval_requested") {
      const done = results.get(d.call_id);
      const resumedAt = done ? (done.data.allowed ? done.ts - done.data.duration : done.ts) : tEnd;
      const wait = Math.max(0, resumedAt - e.ts);
      stats.waitYou += wait;
      add(
        {
          id,
          label: `Waiting for you: ${d.tool}`,
          kind: "wait",
          start: rel(e.ts),
          end: rel(e.ts + wait),
          ongoing: !done,
          lines: [`The ${d.tool} call needed approval.`, done ? `You took ${wait.toFixed(1)}s to decide.` : "Still waiting for a decision."],
        },
        e,
      );
    }

    if (e.type === "retry") {
      const waits = d.kind === "model_error";
      if (waits) stats.waitRetry += d.delay;
      add(
        {
          id,
          label: waits ? `Waiting to retry (${d.attempt} of ${d.max})` : `Retry: broken arguments (${d.attempt} of ${d.max})`,
          kind: waits ? "wait" : "tick",
          start: rel(e.ts),
          end: rel(e.ts + (waits ? d.delay : 0)),
          lines: [waits ? `The model call failed. Waiting ${d.delay}s, then trying again.` : "The model sent invalid JSON and was asked to try again.", `Reason: ${short(d.detail)}`],
        },
        e,
      );
    }

    if (e.type === "compaction_done") {
      stats.modelTime += d.duration;
      stats.promptTokens += d.usage?.prompt ?? 0;
      stats.completionTokens += d.usage?.completion ?? 0;
      stats.cachedTokens += d.usage?.cached ?? 0;
      add(
        {
          id,
          label: "Compaction",
          kind: "compaction",
          start: rel(e.ts - d.duration),
          end: rel(e.ts),
          lines: [`Context went from ${d.before} to ${d.after} tokens.`, `Summary: ${short(d.summary)}`],
        },
        e,
      );
    }

    if (e.type === "hook_ran") {
      add({ id, label: `Hook ${d.hook}: ${d.outcome}`, kind: "tick", start: rel(e.ts), end: rel(e.ts), lines: [`${d.phase} hook on ${d.tool}.`, d.detail || "No detail."] }, e);
    }
    if (e.type === "chaos") {
      add({ id, label: `Break it: ${d.kind}`, kind: "tick", start: rel(e.ts), end: rel(e.ts), lines: [d.detail] }, e);
    }
    if (e.type === "loop_detected") {
      add({ id, label: `Loop detected (${d.count}x)`, kind: "tick", start: rel(e.ts), end: rel(e.ts), lines: [`The same ${d.tool} call was made ${d.count} times and was not run.`] }, e);
    }
    if (e.type === "subagent_started") {
      add({ id, label: "Helper starts", kind: "tick", start: rel(e.ts), end: rel(e.ts), lines: [`Task: ${short(d.task)}`] }, e);
    }
  });

  spans.sort((a, b) => a.start - b.start || a.depth - b.depth);
  return { spans, total: Math.max(tEnd - t0, 0.001), stats };
}
