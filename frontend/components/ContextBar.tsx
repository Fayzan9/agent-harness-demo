import type { Usage } from "@/lib/types";
import { Button, cx } from "./ui";

export const PARTS: { key: string; label: string; color: string }[] = [
  { key: "instructions", label: "Instructions", color: "#94a3b8" },
  { key: "tools", label: "Tool menu", color: "#f5b942" },
  { key: "memory", label: "Memory", color: "#2dbd9b" },
  { key: "summary", label: "Summary", color: "#ec6fa8" },
  { key: "chat", label: "Chat", color: "#8b6cff" },
  { key: "tool_results", label: "Tool results", color: "#f2824b" },
];

type Props = {
  usage?: Usage;
  threshold: number;
  flash: boolean;
  canCompact: boolean;
  queued: boolean;
  onCompact: () => void;
  onSegment: (key: string) => void;
};

export default function ContextBar({ usage, threshold, flash, canCompact, queued, onCompact, onSegment }: Props) {
  const pct = usage ? Math.min(100, Math.round((usage.total / usage.limit) * 100)) : 0;
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-mute">
        <span className="whitespace-nowrap font-medium text-ink">Context window</span>
        <span>{usage ? `${usage.total} of ${usage.limit} tokens (${pct}%)` : "nothing sent yet"}</span>
        <Button className="ml-auto !px-2 !py-0.5 !text-xs" disabled={!canCompact || queued} onClick={onCompact}>
          {queued ? "Queued" : "Compact"}
        </Button>
      </div>
      <div
        className={cx(
          "relative flex h-7 overflow-hidden rounded-lg border bg-bg transition-colors",
          flash ? "border-[#ec6fa8]" : "border-line",
        )}
      >
        {usage &&
          PARTS.map(({ key, label, color }) => {
            const tokens = usage.parts[key] ?? 0;
            return (
              <button
                key={key}
                title={`${label}: ${tokens} tokens. Click to see what is inside.`}
                onClick={() => onSegment(key)}
                className="h-full transition-all duration-300 hover:brightness-110"
                style={{ width: `${(tokens / usage.limit) * 100}%`, background: color }}
              />
            );
          })}
        <div
          title={`Auto-compact at ${threshold}%`}
          className="pointer-events-none absolute inset-y-0 w-px bg-bad"
          style={{ left: `${threshold}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mute">
        {PARTS.map(({ key, label, color }) => (
          <span key={key} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: color }} />
            {label} {usage?.parts[key] ?? 0}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-px bg-bad" /> auto-compact line
        </span>
      </div>
    </div>
  );
}
