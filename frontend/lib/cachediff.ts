import type { ChatMessage, HarnessEvent } from "./types";

export type Status = "same" | "changed" | "new";

export type Pass = {
  messages: ChatMessage[];
  tokens: number[]; // estimated, about 4 characters per token, like the backend
  status: Status[];
  matchedTokens: number;
  totalTokens: number;
  verdict: string;
  hogs: { index: number; label: string; tokens: number; share: number }[];
  reported?: { prompt: number; cached: number; seconds: number }; // what the provider said about this very call
  hasPrevious: boolean;
};

export const approxTokens = (m: ChatMessage) => Math.round(JSON.stringify(m).length / 4);

const mainContexts = (events: HarnessEvent[]) =>
  events.map((e, i) => ({ e, i })).filter(({ e }) => e.type === "context_updated" && e.agent === "main");

/**
 * Compares the latest pass with the one before it, message by message. A provider's prompt cache only helps
 * with an exact match from the very start, so the first difference is where the benefit ends.
 */
export function analyzeLatestPass(events: HarnessEvent[]): Pass | null {
  const contexts = mainContexts(events);
  if (!contexts.length) return null;
  const last = contexts[contexts.length - 1];
  const prev = contexts.length > 1 ? contexts[contexts.length - 2] : null;
  const messages: ChatMessage[] = last.e.data.messages ?? [];
  const before: ChatMessage[] = prev?.e.data.messages ?? [];

  let breakAt = 0;
  if (prev) while (breakAt < before.length && breakAt < messages.length && JSON.stringify(before[breakAt]) === JSON.stringify(messages[breakAt])) breakAt++;

  const status: Status[] = messages.map((_, i) => {
    if (!prev) return "new";
    if (i < breakAt) return "same";
    return i < before.length ? "changed" : "new";
  });
  const tokens = messages.map(approxTokens);
  const totalTokens = tokens.reduce((a, b) => a + b, 0);
  const matchedTokens = tokens.reduce((sum, t, i) => sum + (status[i] === "same" ? t : 0), 0);

  let verdict: string;
  if (!prev) verdict = "First pass of this run, so there is nothing to reuse yet.";
  else if (breakAt === 0) verdict = "The very first message (the instructions) changed, so none of the previous pass can be reused. A clock, date or request id at the top of the prompt does exactly this.";
  else if (breakAt < before.length) {
    const compacted = messages.length < before.length || String(messages[breakAt]?.content ?? "").startsWith("Progress notes");
    verdict = compacted
      ? `Compaction rewrote the older messages from message ${breakAt} onward. The messages before it still match, so those can be reused.`
      : `Message ${breakAt} changed. Everything from there on is read fresh.`;
  } else verdict = "Only new messages were added at the end. Everything before them is an exact repeat, so a provider's cache can serve it.";

  // Name tool results by the tool the model asked for.
  const toolNames = new Map<string, string>();
  for (const m of messages) for (const c of m.tool_calls ?? []) toolNames.set(c.id, c.function.name);
  const hogs = tokens
    .map((t, index) => {
      const m = messages[index];
      const label = m.role === "tool" ? `tool result (${toolNames.get(m.tool_call_id ?? "") ?? "tool"})` : m.role === "system" ? "instructions" : m.role;
      return { index, label, tokens: t, share: totalTokens ? t / totalTokens : 0 };
    })
    .sort((a, b) => b.tokens - a.tokens)
    .slice(0, 3);

  // The model call that followed this snapshot tells us what the provider really cached.
  const reply = events.slice(last.i + 1).find((e) => e.type === "model_replied" && e.agent === "main");
  const reported = reply?.data.usage
    ? { prompt: reply.data.usage.prompt as number, cached: reply.data.usage.cached as number, seconds: reply.data.duration as number }
    : undefined;

  return { messages, tokens, status, matchedTokens, totalTokens, verdict, hogs, reported, hasPrevious: !!prev };
}
