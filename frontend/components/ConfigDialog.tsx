"use client";

import { useEffect, useRef, type ReactNode } from "react";
import type { Stage } from "@/lib/derive";
import type { GateMode, HookInfo, Options, Setup } from "@/lib/types";
import { cx } from "./ui";

export type Target = Stage | "settings";

const TITLES: Record<Target, string> = {
  settings: "Settings",
  agent: "Agent",
  hooksBefore: "Before hooks",
  gate: "Gate",
  tools: "Tools",
  hooksAfter: "After hooks",
  return: "Tools",
  helper: "Helper agent",
};

const INTRO: Record<Target, string> = {
  settings: "Limits, and a way to break things on purpose, for the next run.",
  agent: "The agent is the model. These limits shape what it can hold in mind.",
  hooksBefore: "Run before a tool call. They can block it, and the agent is told why.",
  gate: "Decides whether each tool call may run: automatically, after you approve, or never.",
  tools: "The menu of actions the agent can ask for. It cannot use anything not ticked here.",
  hooksAfter: "Run after a tool call. They can rewrite the result before the agent sees it.",
  return: "The menu of actions the agent can ask for.",
  helper: "Tick delegate to let the agent hand work to a helper with its own fresh context.",
};

const card = "rounded-xl border border-line p-3";
const field = "rounded-lg border border-line bg-bg px-2.5 py-1.5 text-sm outline-none focus:border-accent";

type Props = {
  target: Target | null;
  onClose: () => void;
  options: Options | null;
  setup: Setup;
  setSetup: (s: Setup) => void;
};

export default function ConfigDialog({ target, onClose, options, setup, setSetup }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (target && !d.open) d.showModal();
    if (!target && d.open) d.close();
  }, [target]);

  const toggleTool = (name: string) =>
    setSetup({
      ...setup,
      tools: setup.tools.includes(name) ? setup.tools.filter((t) => t !== name) : [...setup.tools, name],
      gates: { ...setup.gates, [name]: setup.gates[name] ?? "ask" },
    });
  const toggleHook = (h: HookInfo) =>
    setSetup({
      ...setup,
      hooks: setup.hooks.some((x) => x.name === h.name)
        ? setup.hooks.filter((x) => x.name !== h.name)
        : [...setup.hooks, { name: h.name, param: h.param_default ?? undefined }],
    });
  const setParam = (name: string, param: number) =>
    setSetup({ ...setup, hooks: setup.hooks.map((x) => (x.name === name ? { ...x, param } : x)) });

  const tools = (only?: string) => (
    <div className="space-y-2">
      {options?.tools
        .filter((t) => !only || t.name === only)
        .map((t) => (
          <label key={t.name} className={cx(card, "flex cursor-pointer items-start gap-3")}>
            <input type="checkbox" className="mt-1" checked={setup.tools.includes(t.name)} onChange={() => toggleTool(t.name)} />
            <span>
              <span className="font-mono text-sm font-medium">{t.name}</span>
              <span className="block text-xs text-mute">{t.description}</span>
            </span>
          </label>
        ))}
    </div>
  );

  const gates = () =>
    setup.tools.length === 0 ? (
      <p className="text-sm text-mute">No tools are enabled, so there is nothing to gate.</p>
    ) : (
      <div className="space-y-2">
        {setup.tools.map((name) => (
          <div key={name} className={cx(card, "flex items-center justify-between gap-3")}>
            <span className="font-mono text-sm font-medium">{name}</span>
            <select
              className={field}
              value={setup.gates[name] ?? "ask"}
              onChange={(e) => setSetup({ ...setup, gates: { ...setup.gates, [name]: e.target.value as GateMode } })}
            >
              <option value="auto">Run automatically</option>
              <option value="ask">Ask me first</option>
              <option value="block">Always block</option>
            </select>
          </div>
        ))}
      </div>
    );

  const hooks = (phase: "before" | "after") => (
    <div className="space-y-2">
      {options?.hooks
        .filter((h) => h.phase === phase)
        .map((h) => {
          const on = setup.hooks.find((x) => x.name === h.name);
          return (
            <div key={h.name} className={card}>
              <label className="flex cursor-pointer items-start gap-3">
                <input type="checkbox" className="mt-1" checked={!!on} onChange={() => toggleHook(h)} />
                <span>
                  <span className="font-mono text-sm font-medium">{h.name}</span>
                  <span className="block text-xs text-mute">{h.description}</span>
                </span>
              </label>
              {on && h.param_label && (
                <label className="mt-2 ml-7 flex items-center gap-2 text-xs text-mute">
                  {h.param_label}
                  <input
                    type="number"
                    min={1}
                    className={cx(field, "w-24")}
                    value={on.param ?? h.param_default ?? 0}
                    onChange={(e) => setParam(h.name, Number(e.target.value))}
                  />
                </label>
              )}
            </div>
          );
        })}
    </div>
  );

  const toggleChaos = (name: string) =>
    setSetup({
      ...setup,
      chaos: setup.chaos.includes(name) ? setup.chaos.filter((c) => c !== name) : [...setup.chaos, name],
    });

  const number = (value: number, min: number, onChange: (n: number) => void, max?: number) => (
    <input
      type="number"
      min={min}
      max={max}
      className={cx(field, "w-28")}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );

  const limits = (
    <div className="space-y-3">
      <Row label="Model">
        <span className="font-mono text-sm">{options?.models[0] ?? "backend not reachable"}</span>
      </Row>
      <Row label="Context limit (tokens)">{number(setup.context_limit, 300, (n) => setSetup({ ...setup, context_limit: n }))}</Row>
      <Row label="Auto-compact at (%)">{number(setup.compact_at, 10, (n) => setSetup({ ...setup, compact_at: n }), 100)}</Row>
      <Row label="Step limit">{number(setup.max_steps, 1, (n) => setSetup({ ...setup, max_steps: n }))}</Row>
      <Row label="Tool timeout (seconds)">{number(setup.tool_timeout, 1, (n) => setSetup({ ...setup, tool_timeout: n }))}</Row>

      <div className="pt-2">
        <h3 className="text-sm font-semibold">Break it on purpose</h3>
        <p className="mb-2 text-xs text-mute">Inject a failure and watch the harness defend itself.</p>
        <div className="space-y-2">
          {options?.chaos.map((c) => (
            <label key={c.name} className={cx(card, "flex cursor-pointer items-start gap-3")}>
              <input type="checkbox" className="mt-1" checked={setup.chaos.includes(c.name)} onChange={() => toggleChaos(c.name)} />
              <span>
                <span className="font-mono text-sm font-medium">{c.name}</span>
                <span className="block text-xs text-mute">{c.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );

  const body: Record<Target, ReactNode> = {
    settings: limits,
    agent: limits,
    hooksBefore: hooks("before"),
    gate: gates(),
    tools: tools(),
    return: tools(),
    hooksAfter: hooks("after"),
    helper: tools("delegate"),
  };

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto w-[min(520px,92vw)] rounded-2xl border border-line bg-panel p-0 text-ink"
    >
      {target && (
        <div className="max-h-[80vh] overflow-y-auto p-5">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-base font-semibold">{TITLES[target]}</h2>
            <button onClick={onClose} className="text-sm text-mute hover:text-ink" aria-label="Close">
              Close
            </button>
          </div>
          <p className="mb-4 text-sm text-mute">{INTRO[target]} Changes apply to the next run.</p>
          {body[target]}
        </div>
      )}
    </dialog>
  );
}

const Row = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex items-center justify-between gap-4">
    <span className="text-sm">{label}</span>
    {children}
  </div>
);
