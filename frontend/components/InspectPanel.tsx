"use client";

import { useState } from "react";
import { EVENT_COLOR, messageText, summarize, type View } from "@/lib/derive";
import type { HarnessEvent, Usage, WorkspaceFile } from "@/lib/types";
import { PARTS } from "./ContextBar";
import TraceTab from "./TraceTab";
import { Panel, cx } from "./ui";

export type Tab = "events" | "trace" | "context" | "memory" | "files";
const TABS: { id: Tab; label: string }[] = [
  { id: "events", label: "Events" },
  { id: "trace", label: "Trace" },
  { id: "context", label: "Context" },
  { id: "memory", label: "Memory" },
  { id: "files", label: "Files" },
];

type Props = {
  tab: Tab;
  setTab: (t: Tab) => void;
  events: HarnessEvent[];
  view: View;
  memory: string;
  setMemory: (m: string) => void;
  files: WorkspaceFile[];
  focusPart?: string;
};

export default function InspectPanel({ tab, setTab, events, view, memory, setMemory, files, focusPart }: Props) {
  return (
    <Panel
      num={3}
      title="Inspect"
      right={
        <div className="flex gap-1 rounded-lg border border-line bg-bg p-0.5 text-sm">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cx("rounded-md px-3 py-1 font-medium transition", tab === t.id ? "bg-panel text-ink shadow-sm" : "text-mute hover:text-ink")}
            >
              {t.label}
            </button>
          ))}
        </div>
      }
    >
      <div className="h-[520px] overflow-hidden md:h-[370px]">
        {tab === "events" && <EventsTab events={events} />}
        {tab === "trace" && <TraceTab events={events} />}
        {tab === "context" && <ContextTab view={view} focusPart={focusPart} />}
        {tab === "memory" && <MemoryTab memory={memory} setMemory={setMemory} />}
        {tab === "files" && <FilesTab files={files} written={view.written} />}
      </div>
    </Panel>
  );
}

function EventsTab({ events }: { events: HarnessEvent[] }) {
  // Follow the newest event until the user clicks one.
  const [sel, setSel] = useState<{ idx: number; atLen: number } | null>(null);
  const idx = sel && sel.atLen === events.length ? sel.idx : events.length - 1;
  const picked = events[idx];

  if (!events.length) return <Empty>Events appear here as the agent works.</Empty>;
  return (
    <div className="grid h-full grid-rows-2 gap-4 md:grid-cols-[1fr_320px] md:grid-rows-1">
      <ol className="h-full space-y-0.5 overflow-y-auto pr-1">
        {events.map((e, i) => (
          <li key={i}>
            <button
              onClick={() => setSel({ idx: i, atLen: events.length })}
              className={cx(
                "flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition",
                i === idx ? "bg-accent-soft" : "hover:bg-line/40",
                e.agent !== "main" && "ml-4 w-[calc(100%-1rem)]",
              )}
            >
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: EVENT_COLOR[e.type] ?? "var(--mute)" }} />
              <span className="min-w-0">
                <span className="text-xs text-mute">
                  {e.agent !== "main" && "helper · "}
                  {e.type.replace(/_/g, " ")}
                </span>
                <span className="block truncate">{summarize(e)}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      <div className="h-full overflow-y-auto rounded-xl border border-line bg-bg p-3">
        <p className="mb-2 text-xs font-medium text-mute">Selected event: {picked?.type.replace(/_/g, " ")}</p>
        <pre className="whitespace-pre-wrap break-words font-mono text-xs">
          {JSON.stringify({ ...picked?.data, messages: undefined }, null, 2)}
        </pre>
      </div>
    </div>
  );
}

const ROLE_TONE: Record<string, string> = {
  system: "text-mute",
  user: "text-accent",
  assistant: "text-ok",
  tool: "text-warn",
};

function Messages({ usage, title }: { usage?: Usage; title: string }) {
  if (!usage?.messages) return null;
  return (
    <div className="mb-4">
      <p className="mb-2 text-xs font-medium text-mute">{title}: exactly what the model was sent on its latest turn</p>
      <div className="space-y-2">
        {usage.messages.map((m, i) => (
          <div key={i} className="rounded-xl border border-line bg-bg p-2.5">
            <span className={cx("text-xs font-semibold uppercase tracking-wide", ROLE_TONE[m.role])}>{m.role}</span>
            <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-xs">{messageText(m)}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}

function ContextTab({ view, focusPart }: { view: View; focusPart?: string }) {
  if (!view.usage) return <Empty>Run something to see what is inside the context window.</Empty>;
  const part = PARTS.find((p) => p.key === focusPart);
  return (
    <div className="h-full overflow-y-auto pr-1">
      {part && (
        <p className="mb-3 rounded-lg bg-accent-soft px-3 py-2 text-sm">
          <span className="font-semibold">{part.label}</span>: {view.usage.parts[part.key] ?? 0} tokens. Find it below.
          {part.key === "tools" && ` Tool menu: ${view.tools.join(", ") || "none"}.`}
        </p>
      )}
      <Messages usage={view.usage} title="Main agent" />
      <Messages usage={view.subUsage} title="Helper agent" />
    </div>
  );
}

function MemoryTab({ memory, setMemory }: { memory: string; setMemory: (m: string) => void }) {
  return (
    <div className="flex h-full flex-col gap-2">
      <p className="text-sm text-mute">
        The memory file is loaded into context at the start of every run. Edit it here, then run again.
      </p>
      <textarea
        value={memory}
        onChange={(e) => setMemory(e.target.value)}
        className="min-h-0 flex-1 resize-none rounded-xl border border-line bg-bg p-3 font-mono text-sm outline-none focus:border-accent"
        placeholder="Standing instructions, for example: answer in one short sentence."
      />
    </div>
  );
}

function FilesTab({ files, written }: { files: WorkspaceFile[]; written: Set<string> }) {
  const [open, setOpen] = useState<string | null>(null);
  // Show demo files always, and other files only once the replay has reached the write.
  const visible = files.filter((f) => f.seed || written.has(f.name));
  const current = visible.find((f) => f.name === open) ?? visible[0];
  if (!visible.length) return <Empty>The agent has no files to work with yet.</Empty>;
  return (
    <div className="grid h-full grid-rows-2 gap-4 md:grid-cols-[220px_1fr] md:grid-rows-1">
      <ul className="space-y-0.5 overflow-y-auto">
        {visible.map((f) => (
          <li key={f.name}>
            <button
              onClick={() => setOpen(f.name)}
              className={cx(
                "flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left font-mono text-sm",
                f.name === current?.name ? "bg-accent-soft" : "hover:bg-line/40",
              )}
            >
              {f.name}
              {written.has(f.name) && <span className="rounded-full bg-ok-soft px-2 py-0.5 text-[11px] font-sans text-ok">written</span>}
            </button>
          </li>
        ))}
      </ul>
      <pre className="h-full overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-line bg-bg p-3 font-mono text-xs">
        {current?.content}
      </pre>
    </div>
  );
}

const Empty = ({ children }: { children: string }) => (
  <div className="grid h-full place-items-center text-sm text-mute">{children}</div>
);
