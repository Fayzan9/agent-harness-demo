import { buildTrace } from "./trace";
import type { ChatMessage, HarnessEvent, Usage } from "./types";

export type Stage = "agent" | "hooksBefore" | "gate" | "tools" | "hooksAfter" | "return" | "helper";
export type Status = "idle" | "running" | "waiting" | "done" | "error";
export type StageTone = "normal" | "warn" | "bad";

export type View = {
  status: Status;
  stage?: Stage;
  tone: StageTone;
  usage?: Usage;
  subUsage?: Usage;
  tools: string[];
  task?: string;
  answer?: string;
  error?: string;
  pending?: HarnessEvent;
  activity: string;
  helper: boolean;
  compacting: boolean;
  written: Set<string>;
  stats: string;
};

export const EVENT_COLOR: Record<string, string> = {
  run_started: "var(--mute)",
  memory_loaded: "#2dbd9b",
  context_updated: "var(--mute)",
  model_replied: "var(--accent)",
  hook_ran: "var(--warn)",
  gate_checked: "var(--warn)",
  approval_requested: "var(--warn)",
  tool_result: "#f2824b",
  subagent_started: "#8b6cff",
  retry: "var(--warn)",
  chaos: "#ec6fa8",
  loop_detected: "var(--bad)",
  compaction_started: "#ec6fa8",
  compaction_done: "#ec6fa8",
  done: "var(--ok)",
  error: "var(--bad)",
};

export function summarize(e: HarnessEvent): string {
  const d = e.data;
  switch (e.type) {
    case "run_started":
      return `${d.resumed ? "Resumed" : "Run started"} with ${d.model}`;
    case "memory_loaded":
      return `Memory loaded: ${d.text}`;
    case "context_updated":
      return `Context is ${d.total} of ${d.limit} tokens`;
    case "model_replied": {
      const cost = d.usage ? ` (${d.duration}s, ${d.usage.prompt + d.usage.completion} tokens)` : "";
      const calls = d.tool_calls.map((c: { name: string; args: object; error?: string }) =>
        c.error ? `${c.name} with broken arguments` : `${c.name}(${JSON.stringify(c.args)})`,
      );
      return (calls.length ? `Asks to use ${calls.join(", ")}` : `Replies: ${d.text}`) + cost;
    }
    case "retry":
      return d.kind === "model_error"
        ? `Model call failed. Retry ${d.attempt} of ${d.max} in ${d.delay}s: ${d.detail}`
        : `Broken tool arguments. Giving the model another go (${d.attempt} of ${d.max}): ${d.detail}`;
    case "chaos":
      return `Break it: ${d.detail}`;
    case "loop_detected":
      return `Same ${d.tool} call ${d.count} times. It was not run, and the agent was told to try something else.`;
    case "hook_ran":
      return `${d.phase} hook ${d.hook} on ${d.tool}: ${d.outcome}${d.detail ? ` (${d.detail})` : ""}`;
    case "gate_checked":
      return `${d.tool} reaches the "${d.mode}" gate`;
    case "approval_requested":
      return `Waiting for you to approve ${d.tool}`;
    case "tool_result":
      return d.allowed
        ? `${d.tool} returned: ${d.result}${d.duration ? ` (${d.duration}s)` : ""}`
        : `${d.tool} did not run: ${d.result}`;
    case "subagent_started":
      return `Helper starts with a fresh context: ${d.task}`;
    case "compaction_started":
      return `Compacting (${d.reason}). Context is ${d.before} tokens`;
    case "compaction_done":
      return `Context went from ${d.before} to ${d.after} tokens`;
    case "done":
      return d.answer ?? `${d.reason}${d.last_action ? `. Last action: ${d.last_action}` : ""}`;
    default:
      return d.message ?? e.type;
  }
}

function stageOf(e: HarnessEvent): Stage | undefined {
  if (e.agent !== "main") return "helper";
  if (e.type === "hook_ran") return e.data.phase === "before" ? "hooksBefore" : "hooksAfter";
  if (e.type === "loop_detected") return "tools";
  return (
    {
      run_started: "agent",
      memory_loaded: "agent",
      context_updated: "agent",
      compaction_started: "agent",
      compaction_done: "agent",
      model_replied: "agent",
      retry: "agent",
      chaos: "agent",
      subagent_started: "helper",
      gate_checked: "gate",
      approval_requested: "gate",
      tool_result: "return",
    } as Record<string, Stage>
  )[e.type];
}

function activityOf(e?: HarnessEvent): string {
  if (!e) return "";
  const d = e.data;
  if (e.type === "model_replied" && d.tool_calls.length) {
    return `Using ${d.tool_calls.map((c: { name: string }) => c.name).join(", ")}`;
  }
  return (
    {
      retry: d.kind === "model_error" ? "Model failed, retrying" : "Fixing broken arguments",
      chaos: "Something was broken on purpose",
      loop_detected: "Stuck in a loop",
      hook_ran: `Checking the ${d.phase} hook`,
      gate_checked: "At the gate",
      approval_requested: "Waiting for you",
      tool_result: "Got a result",
      compaction_started: "Compacting context",
      compaction_done: "Compacted context",
      subagent_started: "Helper started",
    } as Record<string, string>
  )[e.type] ?? "Thinking";
}

const latestUsage = (events: HarnessEvent[], main: boolean) =>
  [...events].reverse().find((e) => e.type === "context_updated" && (e.agent === "main") === main)?.data as
    | Usage
    | undefined;

function statsOf(events: HarnessEvent[]): string {
  if (!events.length) return "";
  const { total, stats } = buildTrace(events);
  const tokens = stats.promptTokens + stats.completionTokens;
  return [
    `${total.toFixed(1)}s`,
    `${tokens} tokens${stats.cachedTokens ? ` (${stats.cachedTokens} cached)` : ""}`,
    `${stats.modelCalls} model call${stats.modelCalls === 1 ? "" : "s"}`,
    ...(stats.waitYou >= 0.5 ? [`${stats.waitYou.toFixed(1)}s waiting for you`] : []),
  ].join(" · ");
}

/** Everything the screen shows is computed from the events seen so far. That is what makes replay free. */
export function derive(events: HarnessEvent[]): View {
  const last = events.at(-1);
  const answered = new Set(events.filter((e) => e.type === "tool_result").map((e) => e.data.call_id));
  const pending = events.find((e) => e.type === "approval_requested" && !answered.has(e.data.call_id));
  const done = events.find((e) => e.type === "done" && e.agent === "main");
  const error = events.find((e) => e.type === "error" && e.agent === "main");

  const paths = new Map<string, string>();
  const written = new Set<string>();
  for (const e of events) {
    if (e.type === "model_replied") {
      for (const c of e.data.tool_calls) if (c.name === "write_file") paths.set(c.id, c.args.path);
    }
    if (e.type === "tool_result" && e.data.tool === "write_file" && e.data.allowed && paths.has(e.data.call_id)) {
      if (!String(e.data.result).startsWith("Error")) written.add(paths.get(e.data.call_id)!);
    }
  }

  let status: Status = "running";
  if (!events.length) status = "idle";
  else if (error) status = "error";
  else if (done) status = "done";
  else if (pending) status = "waiting";

  let tone: StageTone = "normal";
  if (last?.type === "hook_ran" && last.data.outcome === "blocked") tone = "bad";
  else if (pending && last?.type === "approval_requested") tone = "warn";
  else if (last?.type === "retry" || last?.type === "chaos") tone = "warn";
  else if (last?.type === "loop_detected") tone = "bad";

  const answer = done
    ? (done.data.answer ?? `Stopped: ${done.data.reason}${done.data.last_action ? `. Last action: ${done.data.last_action}` : ""}`)
    : undefined;

  return {
    status,
    stage: last && stageOf(last),
    tone,
    usage: latestUsage(events, true),
    subUsage: latestUsage(events, false),
    tools: events[0]?.data.tools ?? [],
    task: events[0]?.data.task,
    answer,
    error: error?.data.message,
    pending,
    activity: activityOf(last),
    helper: events.some((e) => e.agent !== "main"),
    compacting: last?.type === "compaction_started" || last?.type === "compaction_done",
    written,
    stats: statsOf(events),
  };
}

export const messageText = (m: ChatMessage): string => {
  const calls = (m.tool_calls ?? []).map((c) => `${c.function.name}(${c.function.arguments})`).join("\n");
  return [m.content, calls].filter(Boolean).join("\n");
};
