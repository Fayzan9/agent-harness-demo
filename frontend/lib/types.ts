export type GateMode = "auto" | "ask" | "block";

export type HarnessEvent = {
  type: string;
  step: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>;
  ts: number;
  agent: string; // "main" or a subagent id
};

export type ChatMessage = {
  role: string;
  content: string | null;
  tool_calls?: { id: string; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
};

export type Usage = {
  limit: number;
  total: number;
  parts: Record<string, number>;
  messages?: ChatMessage[]; // exactly what the model was sent
};

export type Turn = { runId: string; task: string; events: HarnessEvent[] };

export type InterruptedAt = { tool: string; state: string };

export type SessionSummary = {
  id: string;
  title: string;
  created: number;
  updated: number;
  status: "idle" | "running" | "interrupted";
  turns: number;
  interrupted_at: InterruptedAt | null;
};

export type SessionDetail = {
  id: string;
  title: string;
  status: string;
  interrupted_at: InterruptedAt | null;
  setup: Setup | null;
  turns: { run_id: string; task: string; events: HarnessEvent[] }[];
};

export type WorkspaceFile = { name: string; content: string; seed: boolean };

/** Everything the user can set except the task, which comes from the chat box. */
export type Setup = Omit<RunConfig, "task">;

export type HookInfo = {
  name: string;
  phase: "before" | "after";
  description: string;
  param_label: string | null;
  param_default: number | null;
};

export type HookSetting = { name: string; param?: number };

export type Options = {
  models: string[];
  gate_modes: GateMode[];
  hooks: HookInfo[];
  chaos: { name: string; description: string }[];
  tools: { name: string; description: string }[];
};

export type RunConfig = {
  task: string;
  tools: string[];
  gates: Record<string, GateMode>;
  hooks: HookSetting[];
  memory: string;
  context_limit: number;
  compact_at: number;
  max_steps: number;
  tool_timeout: number;
  chaos: string[];
};

export type EvalKind = "outcome" | "trajectory" | "judge";

export type EvalCase = { id: string; label: string; task: string; checks: { kind: EvalKind; label: string }[] };

export type EvalVariant = { id: string; label: string; description: string };

export type EvalOptions = { cases: EvalCase[]; variants: EvalVariant[] };

export type EvalRun = {
  case: string;
  variant: string;
  index: number;
  passed: boolean;
  checks: { kind: EvalKind; label: string; passed: boolean; detail: string }[];
  seconds: number;
  tokens: number;
  answer: string;
  events: HarnessEvent[];
};

export type EvalStream = { type: "plan"; total: number } | ({ type: "run_done" } & EvalRun) | { type: "done" };
