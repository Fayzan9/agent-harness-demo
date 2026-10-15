"use client";

import { useMemo, useState } from "react";
import { buildTrace, type SpanKind } from "@/lib/trace";
import type { HarnessEvent } from "@/lib/types";
import { cx } from "./ui";

const KIND: Record<SpanKind, { color: string; label: string }> = {
  model: { color: "#7F77DD", label: "Model call" },
  tool: { color: "#D85A30", label: "Tool" },
  helper: { color: "#1D9E75", label: "Helper agent" },
  wait: { color: "#E5A23B", label: "Waiting" },
  compaction: { color: "#ec6fa8", label: "Compaction" },
  tick: { color: "#94a3b8", label: "Hook or event" },
};

const secs = (n: number) => `${n.toFixed(n < 10 ? 2 : 1)}s`;

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-bg px-3 py-2">
      <p className="text-[11px] text-mute">{label}</p>
      <p className="text-sm font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-mute">{hint}</p>}
    </div>
  );
}

export default function TraceTab({ events }: { events: HarnessEvent[] }) {
  const { spans, total, stats } = useMemo(() => buildTrace(events), [events]);
  const [selId, setSelId] = useState<string | null>(null);

  if (!events.length) {
    return <div className="grid h-full place-items-center text-sm text-mute">Run something to see where the time goes.</div>;
  }

  const timed = spans.filter((s) => s.kind === "model" || s.kind === "tool" || s.kind === "compaction");
  const slowest = timed.reduce<(typeof spans)[number] | undefined>((a, s) => (!a || s.end - s.start > a.end - a.start ? s : a), undefined);
  const picked = spans.find((s) => s.id === selId) ?? slowest ?? spans[spans.length - 1];
  const waiting = stats.waitYou + stats.waitRetry;
  const cacheHint = stats.cachedTokens
    ? `${Math.round((stats.cachedTokens / Math.max(stats.promptTokens, 1)) * 100)}% of input`
    : "none reported";

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
        <Stat label="Total" value={secs(total)} />
        <Stat label="Model" value={secs(stats.modelTime)} hint={`${stats.modelCalls} calls`} />
        <Stat label="Tools" value={secs(stats.toolTime)} />
        <Stat label="Waiting" value={secs(waiting)} hint="you and retries" />
        <Stat label="Tokens" value={`${stats.promptTokens} in`} hint={`${stats.completionTokens} out`} />
        <Stat label="Cache" value={`${stats.cachedTokens}`} hint={cacheHint} />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-mute">
        {(Object.keys(KIND) as SpanKind[]).map((k) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: KIND[k].color }} />
            {KIND[k].label}
          </span>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[1fr_270px]">
        <ol className="min-h-0 space-y-0.5 overflow-y-auto pr-1">
          {spans.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => setSelId(s.id)}
                className={cx(
                  "grid w-full grid-cols-[150px_1fr] items-center gap-2 rounded-lg px-2 py-1 text-left text-xs transition md:grid-cols-[190px_1fr]",
                  s.id === picked?.id ? "bg-accent-soft" : "hover:bg-line/40",
                )}
              >
                <span className="truncate" style={{ paddingLeft: s.depth * 14 }}>
                  {s.label}
                  {s === slowest && <span className="ml-1.5 rounded-full bg-warn-soft px-1.5 py-0.5 text-[10px] text-warn">slowest</span>}
                </span>
                <span className="relative h-4 rounded bg-line/50">
                  <span
                    className={cx("absolute inset-y-0.5 rounded-sm", s.ongoing && "animate-pulse")}
                    style={{
                      left: `${(s.start / total) * 100}%`,
                      width: `${Math.max(((s.end - s.start) / total) * 100, 0.8)}%`,
                      minWidth: 3,
                      background: KIND[s.kind].color,
                    }}
                  />
                </span>
              </button>
            </li>
          ))}
        </ol>

        <div className="min-h-0 overflow-y-auto rounded-xl border border-line bg-bg p-3 text-sm">
          {picked && (
            <>
              <p className="font-semibold">{picked.label}</p>
              <p className="mb-2 text-xs text-mute">
                {picked.end - picked.start > 0.004
                  ? `starts at ${secs(picked.start)}, takes ${secs(picked.end - picked.start)}`
                  : `at ${secs(picked.start)}`}
                {picked.ongoing && " (still going)"}
              </p>
              {picked.lines.map((l, i) => (
                <p key={i} className="mb-1 break-words text-xs">
                  {l}
                </p>
              ))}
            </>
          )}
        </div>
      </div>

      {stats.cachedTokens === 0 && stats.promptTokens > 0 && (
        <p className="text-[11px] text-mute">
          No cached tokens reported. Providers usually only cache longer prompts (often above roughly a thousand tokens), so short demo runs show none. Check your provider&apos;s rule.
        </p>
      )}
    </div>
  );
}
