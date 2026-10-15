import type { Status } from "@/lib/derive";
import { CUSTOM_ID, type Scenario } from "@/lib/scenarios";
import { Button, Chip, cx, type Tone } from "./ui";

const STATUS: Record<Status, { label: string; tone: Tone }> = {
  idle: { label: "Ready", tone: "neutral" },
  running: { label: "Running", tone: "accent" },
  waiting: { label: "Your turn", tone: "warn" },
  done: { label: "Done", tone: "ok" },
  error: { label: "Error", tone: "bad" },
};

type Props = {
  scenarios: Scenario[];
  scenarioId: string;
  onScenario: (id: string) => void;
  mode: "auto" | "step";
  onMode: (m: "auto" | "step") => void;
  onSettings: () => void;
  onHistory: () => void;
  status: Status;
  stats: string;
};

export default function TopBar({ scenarios, scenarioId, onScenario, mode, onMode, onSettings, onHistory, status, stats }: Props) {
  const current = scenarios.find((s) => s.id === scenarioId);
  return (
    <header className="flex flex-wrap items-center gap-3">
      <h1 className="mr-2 text-lg font-semibold tracking-tight">Agent harness</h1>

      <label className="flex min-w-[240px] flex-col">
        <select
          value={scenarioId}
          onChange={(e) => onScenario(e.target.value)}
          className="rounded-lg border border-line bg-panel px-3 py-1.5 text-sm font-medium outline-none focus:border-accent"
          aria-label="Scenario"
        >
          {(["Lessons", "Break it"] as const).map((g) => (
            <optgroup key={g} label={g}>
              {scenarios
                .filter((s) => s.group === g)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
            </optgroup>
          ))}
          {scenarioId === CUSTOM_ID && <option value={CUSTOM_ID}>Custom setup</option>}
        </select>
      </label>

      <div className="flex rounded-lg border border-line bg-panel p-0.5 text-sm font-medium" role="group" aria-label="Playback mode">
        {(["auto", "step"] as const).map((m) => (
          <button
            key={m}
            onClick={() => onMode(m)}
            className={cx("rounded-md px-3 py-1 capitalize transition", mode === m ? "bg-accent text-white" : "text-mute hover:text-ink")}
          >
            {m}
          </button>
        ))}
      </div>

      <Button onClick={onSettings}>Settings</Button>
      <Button onClick={onHistory}>History</Button>
      <div className="ml-auto flex items-center gap-3">
        {stats && <span className="text-xs tabular-nums text-mute">{stats}</span>}
        <Chip tone={STATUS[status].tone}>{STATUS[status].label}</Chip>
      </div>

      {current && <p className="basis-full text-sm text-mute">{current.blurb}</p>}
    </header>
  );
}
