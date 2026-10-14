import { Button, cx } from "./ui";

type Props = {
  shown: number;
  total: number;
  mode: "auto" | "step";
  playing: boolean;
  onBack: () => void;
  onNext: () => void;
  onPlay: () => void;
  onScrub: (i: number) => void;
};

export default function ReplayBar({ shown, total, mode, playing, onBack, onNext, onPlay, onScrub }: Props) {
  return (
    <div className="z-10 md:sticky md:bottom-4 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-panel/95 p-3 shadow-lg backdrop-blur">
      <span className="grid h-5 w-5 place-items-center rounded-full bg-accent text-[11px] font-semibold text-white">4</span>
      <span className="text-sm font-semibold">Replay</span>
      <Button onClick={onBack} disabled={shown === 0}>
        Back
      </Button>
      <Button variant={mode === "step" ? "primary" : "ghost"} onClick={onNext} disabled={shown >= total}>
        Next
      </Button>
      <Button onClick={onPlay} disabled={total === 0}>
        {playing ? "Pause" : "Play"}
      </Button>
      <input
        type="range"
        min={0}
        max={Math.max(total, 1)}
        value={shown}
        onChange={(e) => onScrub(Number(e.target.value))}
        disabled={total === 0}
        className="min-w-[160px] flex-1"
        aria-label="Event position"
      />
      <span className={cx("w-28 text-right text-sm tabular-nums", total ? "text-ink" : "text-mute")}>
        {total ? `Event ${shown} of ${total}` : "No run yet"}
      </span>
    </div>
  );
}
