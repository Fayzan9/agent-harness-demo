import type { Setup } from "./types";

export type Scenario = { id: string; group: "Lessons" | "Break it"; label: string; blurb: string; task: string; setup: Setup };

const base: Setup = {
  tools: [],
  gates: {},
  hooks: [],
  memory: "Answer in one short sentence.",
  context_limit: 8000,
  compact_at: 80,
  max_steps: 10,
  tool_timeout: 20,
  chaos: [],
};

export const SCENARIOS: Scenario[] = [
  {
    id: "loop",
    group: "Lessons",
    label: "The loop: read a file",
    blurb: "Ask, use a tool, answer. The smallest complete loop.",
    task: "Read notes.txt and tell me who owns it.",
    setup: { ...base, tools: ["list_files", "read_file"], gates: { list_files: "auto", read_file: "auto" } },
  },
  {
    id: "gate",
    group: "Lessons",
    label: "Gate asks permission",
    blurb: "Writing a file needs your approval. Reading does not.",
    task: "Create a file called hello.txt that says: Hello from the harness.",
    setup: { ...base, tools: ["read_file", "write_file"], gates: { read_file: "auto", write_file: "ask" } },
  },
  {
    id: "block",
    group: "Lessons",
    label: "Hook blocks .env",
    blurb: "A before hook stops the call. The agent is told why.",
    task: "Read the file .env and tell me what is inside.",
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, hooks: [{ name: "block_sensitive_files" }] },
  },
  {
    id: "redact",
    group: "Lessons",
    label: "Hook hides emails",
    blurb: "An after hook rewrites the result before the agent sees it.",
    task: "Read contact.txt and repeat it back exactly.",
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, hooks: [{ name: "redact_emails" }] },
  },
  {
    id: "compact",
    group: "Lessons",
    label: "Context fills, then compacts",
    blurb: "A tiny context limit forces automatic compaction.",
    task: "Read notes.txt and contact.txt, then write a one-line summary of both to summary.txt.",
    setup: {
      ...base,
      tools: ["list_files", "read_file", "write_file"],
      gates: { list_files: "auto", read_file: "auto", write_file: "auto" },
      context_limit: 700,
      compact_at: 55,
    },
  },
  {
    id: "helper",
    group: "Lessons",
    label: "Helper agent",
    blurb: "The agent hands work to a helper with its own fresh context.",
    task: "Use the delegate tool to have a helper agent read notes.txt and report who owns it. Then tell me.",
    setup: {
      ...base,
      tools: ["delegate", "list_files", "read_file"],
      gates: { delegate: "auto", list_files: "auto", read_file: "auto" },
    },
  },
  {
    id: "chaos-rate",
    group: "Break it",
    label: "The API says 429",
    blurb: "The model API refuses twice. The harness waits and retries.",
    task: "Read notes.txt and tell me who owns it.",
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, chaos: ["rate_limit"] },
  },
  {
    id: "chaos-json",
    group: "Break it",
    label: "Broken tool arguments",
    blurb: "The tool call arrives as invalid JSON. The model gets up to three chances to fix it.",
    task: "Read notes.txt and tell me who owns it.",
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, chaos: ["bad_json"] },
  },
  {
    id: "chaos-slow",
    group: "Break it",
    label: "A tool hangs",
    blurb: "The tool never answers. A timeout cuts it off and the agent tries again.",
    task: "Read notes.txt and tell me who owns it.",
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, tool_timeout: 4, chaos: ["slow_tool"] },
  },
  {
    id: "chaos-loop",
    group: "Break it",
    label: "Stuck in a loop",
    blurb: "The agent repeats one call. It is warned, then stopped.",
    task: "Read notes.txt and tell me who owns it.",
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, chaos: ["repeat_call"] },
  },
];

export const CUSTOM_ID = "custom";
