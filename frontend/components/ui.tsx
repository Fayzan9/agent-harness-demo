import type { ButtonHTMLAttributes, ReactNode } from "react";

export const cx = (...parts: (string | false | undefined | null)[]) => parts.filter(Boolean).join(" ");

export type Tone = "neutral" | "accent" | "warn" | "ok" | "bad";

const TONES: Record<Tone, string> = {
  neutral: "bg-line/60 text-mute",
  accent: "bg-accent-soft text-accent",
  warn: "bg-warn-soft text-warn",
  ok: "bg-ok-soft text-ok",
  bad: "bg-bad-soft text-bad",
};

export function Chip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", TONES[tone])}>
      {children}
    </span>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" };

export function Button({ variant = "ghost", className, ...props }: ButtonProps) {
  const styles = {
    primary: "bg-accent text-white hover:opacity-90",
    ghost: "border border-line bg-panel text-ink hover:bg-line/40",
    danger: "bg-bad text-white hover:opacity-90",
  }[variant];
  return (
    <button
      className={cx(
        "rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40",
        styles,
        className,
      )}
      {...props}
    />
  );
}

type PanelProps = { num: number; title: string; hint?: string; right?: ReactNode; children: ReactNode; className?: string };

export function Panel({ num, title, hint, right, children, className }: PanelProps) {
  return (
    <section className={cx("rounded-2xl border border-line bg-panel p-4", className)}>
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <span className="grid h-5 w-5 place-items-center rounded-full bg-accent text-[11px] font-semibold text-white">
          {num}
        </span>
        <h2 className="text-sm font-semibold">{title}</h2>
        {hint && <span className="text-xs text-mute">{hint}</span>}
        <div className="ml-auto">{right}</div>
      </header>
      {children}
    </section>
  );
}
