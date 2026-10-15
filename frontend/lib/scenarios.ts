import type { Setup } from "./types";

export type Scenario = { id: string; group: "Lessons" | "Break it" | "Context"; label: string; blurb: string; task: string; setup: Setup };

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

// About 1,100 tokens of standing instructions, enough for a provider's prompt cache to kick in.
const LONG_MEMORY = Array.from({ length: 90 }, (_, i) => `Rule ${i + 1}: Check the facts twice before answering and keep replies short.`).join("\n");

const readTwoFiles = "Read notes.txt and contact.txt, then tell me who owns the demo and the contact email.";
const refundTask = "Find the refund policy in handbook.txt and tell me how many days customers have to return items.";

SCENARIOS.push(
  {
    id: "ctx-big-read",
    group: "Context",
    label: "Big file: read it all",
    blurb: "Without a search tool the whole handbook lands in context. Watch Tool results in the context bar.",
    task: refundTask,
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" } },
  },
  {
    id: "ctx-big-search",
    group: "Context",
    label: "Big file: search instead",
    blurb: "With search_file the agent loads only the line it needs. Same answer, a fraction of the context.",
    task: refundTask,
    setup: { ...base, tools: ["read_file", "search_file"], gates: { read_file: "auto", search_file: "auto" } },
  },
  {
    id: "ctx-big-cut",
    group: "Context",
    label: "Big file: cut at 800 characters",
    blurb: "Blind trimming is not free. The agent pages through the file anyway, and can still miss the answer.",
    task: refundTask,
    setup: { ...base, tools: ["read_file"], gates: { read_file: "auto" }, hooks: [{ name: "truncate_result", param: 800 }] },
  },
  {
    id: "ctx-cache-stable",
    group: "Context",
    label: "Cache: a stable prefix",
    blurb: "Long standing instructions repeat on every pass. Open Inspect > Context to see the provider serve them from cache.",
    task: readTwoFiles,
    setup: { ...base, tools: ["list_files", "read_file"], gates: { list_files: "auto", read_file: "auto" }, memory: LONG_MEMORY },
  },
  {
    id: "ctx-cache-clock",
    group: "Context",
    label: "Cache breaker: clock in the prompt",
    blurb: "The same run, with the time at the very top of the instructions. The start changes every pass, so nothing is cached.",
    task: readTwoFiles,
    setup: {
      ...base,
      tools: ["list_files", "read_file"],
      gates: { list_files: "auto", read_file: "auto" },
      memory: LONG_MEMORY,
      chaos: ["clock_in_prompt"],
    },
  },
  {
    id: "ctx-notes",
    group: "Context",
    label: "Notes outlive compaction",
    blurb: "A tiny context forces compaction. Facts saved to the scratchpad file are still there afterwards.",
    task: "Read notes.txt and contact.txt and save the key facts as notes. Then tell me who owns the demo and the contact email.",
    setup: {
      ...base,
      tools: ["list_files", "read_file", "save_note", "read_notes"],
      gates: { list_files: "auto", read_file: "auto", save_note: "auto", read_notes: "auto" },
      context_limit: 700,
      compact_at: 50,
    },
  },
);

export const CUSTOM_ID = "custom";
