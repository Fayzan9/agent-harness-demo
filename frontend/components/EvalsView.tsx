"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getEvalOptions, streamEvals } from "@/lib/api";
import type { EvalKind, EvalOptions, EvalRun, HarnessEvent } from "@/lib/types";
import { Button, Chip, Panel, cx, type Tone } from "./ui";

const KIND_TONE: Record<EvalKind, Tone> = { outcome: "accent", trajectory: "neutral", judge: "ok" };
const BIG_RUN = 12; // above this, ask for a second click before spending the quota

type Pick = { case: string; variant: string; index: number };
type Status = "idle" | "running" | "done" | "stopped" | "error";

type Props = { onReplay: (task: string, events: HarnessEvent[]) => void };

export default function EvalsView({ onReplay }: Props) {
  const [options, setOptions] = useState<EvalOptions | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [a, setA] = useState("baseline");
  const [b, setB] = useState("no_hooks"); // "" means no comparison
  const [perCase, setPerCase] = useState(3);
  const [results, setResults] = useState<EvalRun[]>([]);
  const [planned, setPlanned] = useState({ cases: [] as string[], variants: [] as string[], runs: 0, total: 0 });
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [armedFor, setArmedFor] = useState<number | null>(null); // the run count the user has been warned about
  const [pick, setPick] = useState<Pick | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    getEvalOptions()
      .then((o) => {
        setOptions(o);
        setChosen(new Set(o.cases.map((c) => c.id)));
      })
      .catch(() => setMessage("Could not reach the backend."));
  }, []);

  const variants = useMemo(() => [a, ...(b && b !== a ? [b] : [])], [a, b]);
  const total = chosen.size * variants.length * perCase;
  const running = status === "running";
  const armed = armedFor === total; // changing the selection withdraws the warning
  const label = (id: string) => options?.variants.find((v) => v.id === id)?.label ?? id;
  const caseLabel = (id: string) => options?.cases.find((c) => c.id === id)?.label ?? id;

  const toggle = (id: string) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const start = async () => {
    if (total > BIG_RUN && !armed) {
      setArmedFor(total);
      return;
    }
    setArmedFor(null);
    const cases = options!.cases.filter((c) => chosen.has(c.id)).map((c) => c.id);
    setResults([]);
    setPick(null);
    setMessage("");
    setPlanned({ cases, variants, runs: perCase, total });
    setStatus("running");
    abort.current = new AbortController();
    try {
      for await (const e of streamEvals({ cases, variants, runs: perCase }, abort.current.signal)) {
        if (e.type === "run_done") setResults((r) => [...r, e]);
        if (e.type === "done") setStatus("done");
      }
      setStatus((s) => (s === "running" ? "done" : s));
    } catch (err) {
      if ((err as Error).name === "AbortError") setStatus("stopped");
      else {
        setStatus("error");
        setMessage((err as Error).message);
      }
    }
  };

  const stop = () => abort.current?.abort();

  const runsOf = (c: string, v: string) => results.filter((r) => r.case === c && r.variant === v).sort((x, y) => x.index - y.index);
  const rate = (c: string, v: string) => {
    const rs = runsOf(c, v);
    return rs.length === planned.runs ? (rs.filter((r) => r.passed).length / planned.runs) * 100 : null;
  };
  const picked = pick ? results.find((r) => r.case === pick.case && r.variant === pick.variant && r.index === pick.index) : undefined;
  const compare = planned.variants.length === 2;
  const done = results.length;

  const overall = (v: string) => {
    const rs = results.filter((r) => r.variant === v);
    return rs.length ? Math.round((rs.filter((r) => r.passed).length / rs.length) * 100) : null;
  };

  return (
    <div className="flex flex-col gap-4">
      <Panel num={1} title="Choose" hint="Change one thing, run again, compare the score">
        <p className="mb-4 text-sm text-mute">
          An eval runs the same tasks several times and checks each run automatically.{" "}
          <span className="text-ink">Outcome</span> checks the result, <span className="text-ink">trajectory</span> checks how it got there, and a{" "}
          <span className="text-ink">judge</span> lets a model grade what has no exact answer. Try Baseline against Without hooks.
        </p>

        <div className="mb-4 flex items-center gap-3 text-xs text-mute">
          <button className="underline" onClick={() => setChosen(new Set(options?.cases.map((c) => c.id)))}>
            Select all
          </button>
          <button className="underline" onClick={() => setChosen(new Set())}>
            Select none
          </button>
        </div>

        <ul className="grid gap-2 md:grid-cols-2">
          {options?.cases.map((c) => {
            const counts = (["outcome", "trajectory", "judge"] as EvalKind[])
              .map((k) => [k, c.checks.filter((x) => x.kind === k).length] as const)
              .filter(([, n]) => n > 0);
            return (
              <li key={c.id}>
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line p-3">
                  <input type="checkbox" className="mt-1" checked={chosen.has(c.id)} onChange={() => toggle(c.id)} />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{c.label}</span>
                    <span className="block truncate text-xs text-mute">{c.task}</span>
                    <span className="mt-1.5 flex flex-wrap gap-1.5">
                      {counts.map(([k, n]) => (
                        <Chip key={k} tone={KIND_TONE[k]}>
                          {n} {k}
                        </Chip>
                      ))}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          {[
            ["Setup A", a, setA, false],
            ["Setup B (compare)", b, setB, true],
          ].map(([title, value, set, optional]) => (
            <label key={title as string} className="flex flex-col gap-1 text-sm font-medium">
              {title as string}
              <select
                value={value as string}
                onChange={(e) => (set as (v: string) => void)(e.target.value)}
                className="rounded-lg border border-line bg-bg px-2.5 py-1.5 text-sm font-normal outline-none focus:border-accent"
              >
                {optional && <option value="">No comparison</option>}
                {options?.variants.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
              <span className="text-xs font-normal text-mute">
                {options?.variants.find((v) => v.id === value)?.description ?? "Run only Setup A"}
              </span>
            </label>
          ))}
          <div className="flex flex-col gap-1 text-sm font-medium">
            Runs per case
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => setPerCase(n)}
                  className={cx(
                    "h-8 w-8 rounded-lg border text-sm font-medium",
                    perCase === n ? "border-accent bg-accent-soft text-accent" : "border-line text-mute",
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
            <span className="text-xs font-normal text-mute">Models vary, so one run proves little.</span>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          {running ? (
            <Button variant="danger" onClick={stop}>
              Stop
            </Button>
          ) : (
            <Button variant="primary" onClick={start} disabled={!options || total === 0}>
              {armed && total > BIG_RUN ? `Confirm: run ${total}` : "Run evals"}
            </Button>
          )}
          <span className="text-sm text-mute">
            {chosen.size} {chosen.size === 1 ? "case" : "cases"} × {perCase} runs × {variants.length} {variants.length === 1 ? "setup" : "setups"} ={" "}
            <span className="font-medium text-ink">{total} runs</span>, roughly {total * 3} model calls on your Azure quota
            {armed && total > BIG_RUN && ". That is a lot. Click again to confirm."}
          </span>
        </div>
      </Panel>

      <Panel
        num={2}
        title="Results"
        hint={running ? `${done} of ${planned.total} runs finished` : status === "idle" ? "Nothing run yet" : status}
        right={
          status === "done" && results.length ? (
            <Chip tone="neutral">
              {results.reduce((s, r) => s + r.tokens, 0)} tokens · {results.reduce((s, r) => s + r.seconds, 0).toFixed(0)}s of runs
            </Chip>
          ) : undefined
        }
      >
        {message && <p className="mb-3 text-sm text-bad">{message}</p>}
        {planned.total === 0 && !message && <p className="text-sm text-mute">Run the evals to fill in this grid. Each dot is one run. Click a dot to look inside.</p>}

        {planned.total > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="text-left text-xs text-mute">
                  <th className="pb-2 font-medium">Case</th>
                  {planned.variants.map((v) => (
                    <th key={v} className="pb-2 font-medium">
                      {label(v)}
                    </th>
                  ))}
                  {compare && <th className="pb-2 font-medium">Change</th>}
                </tr>
              </thead>
              <tbody>
                {planned.cases.map((c) => {
                  const ra = rate(c, planned.variants[0]);
                  const rb = compare ? rate(c, planned.variants[1]) : null;
                  const delta = ra !== null && rb !== null ? Math.round(rb - ra) : null;
                  return (
                    <tr key={c} className="border-t border-line">
                      <td className="py-2.5 pr-3 font-medium">{caseLabel(c)}</td>
                      {planned.variants.map((v) => (
                        <td key={v} className="py-2.5 pr-3">
                          <RateCell
                            runs={runsOf(c, v)}
                            total={planned.runs}
                            running={running}
                            picked={pick?.case === c && pick.variant === v ? pick.index : undefined}
                            onPick={(index) => setPick({ case: c, variant: v, index })}
                          />
                        </td>
                      ))}
                      {compare && (
                        <td className="py-2.5">
                          {delta === null ? (
                            <span className="text-mute">...</span>
                          ) : (
                            <span className={cx("font-medium", delta < 0 ? "text-bad" : delta > 0 ? "text-ok" : "text-mute")}>
                              {delta === 0 ? "Same" : `${delta > 0 ? "+" : ""}${delta}%`}
                            </span>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
                <tr className="border-t-2 border-line text-sm font-semibold">
                  <td className="py-2.5">All cases</td>
                  {planned.variants.map((v) => (
                    <td key={v} className="py-2.5">
                      {overall(v) === null ? "..." : `${overall(v)}% pass`}
                    </td>
                  ))}
                  {compare && (
                    <td className="py-2.5">
                      {overall(planned.variants[0]) !== null && overall(planned.variants[1]) !== null
                        ? `${(overall(planned.variants[1])! - overall(planned.variants[0])!) > 0 ? "+" : ""}${overall(planned.variants[1])! - overall(planned.variants[0])!}%`
                        : ""}
                    </td>
                  )}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel num={3} title="Inspect a run" hint={picked ? undefined : "Click a dot in the grid"}>
        {!picked && <p className="text-sm text-mute">Failed runs are the interesting ones. Open one to see which check failed, then replay it step by step.</p>}
        {picked && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-semibold">{caseLabel(picked.case)}</span>
              <span className="text-mute">
                {label(picked.variant)} · run {picked.index + 1}
              </span>
              <Chip tone={picked.passed ? "ok" : "bad"}>{picked.passed ? "Passed" : "Failed"}</Chip>
              <span className="text-xs text-mute">
                {picked.seconds}s · {picked.tokens} tokens
              </span>
              <Button
                className="ml-auto !px-2.5 !py-1 !text-xs"
                onClick={() => onReplay(`${caseLabel(picked.case)} (${label(picked.variant)}, run ${picked.index + 1})`, picked.events)}
              >
                Replay this run
              </Button>
            </div>
            <ul className="space-y-1.5">
              {picked.checks.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className={cx("mt-0.5 w-4 shrink-0 font-semibold", c.passed ? "text-ok" : "text-bad")}>{c.passed ? "✓" : "✗"}</span>
                  <span className="min-w-0">
                    <Chip tone={KIND_TONE[c.kind]}>{c.kind}</Chip> <span>{c.label}</span>
                    {!c.passed && c.detail && <span className="block text-xs text-mute">{c.detail}</span>}
                  </span>
                </li>
              ))}
            </ul>
            <div className="rounded-xl border border-line bg-bg p-3 text-sm">
              <p className="mb-1 text-xs font-medium text-mute">The agent&apos;s final answer</p>
              {picked.answer || <span className="text-mute">(no answer)</span>}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function RateCell({
  runs,
  total,
  running,
  picked,
  onPick,
}: {
  runs: EvalRun[];
  total: number;
  running: boolean;
  picked?: number;
  onPick: (index: number) => void;
}) {
  const passes = runs.filter((r) => r.passed).length;
  const finished = runs.length === total;
  return (
    <div className="flex items-center gap-3">
      <span className={cx("w-10 font-semibold tabular-nums", !finished ? "text-mute" : passes === total ? "text-ok" : passes === 0 ? "text-bad" : "text-warn")}>
        {passes}/{total}
      </span>
      <span className="flex gap-1.5">
        {Array.from({ length: total }, (_, i) => {
          const r = runs.find((x) => x.index === i);
          return (
            <button
              key={i}
              disabled={!r}
              onClick={() => onPick(i)}
              title={r ? `Run ${i + 1}: ${r.passed ? "passed" : "failed"}. Click to inspect.` : "Waiting"}
              className={cx(
                "h-3.5 w-3.5 rounded-full transition",
                r ? (r.passed ? "bg-ok" : "bg-bad") : cx("bg-line", running && "animate-pulse"),
                picked === i && "ring-2 ring-accent ring-offset-2 ring-offset-panel",
              )}
            />
          );
        })}
      </span>
    </div>
  );
}
