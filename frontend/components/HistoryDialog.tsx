"use client";

import { useEffect, useRef } from "react";
import type { SessionSummary } from "@/lib/types";
import { Chip, cx, type Tone } from "./ui";

const STATUS: Record<SessionSummary["status"], { label: string; tone: Tone }> = {
  idle: { label: "Finished", tone: "neutral" },
  running: { label: "Running", tone: "accent" },
  interrupted: { label: "Stopped part-way", tone: "warn" },
};

type Props = {
  open: boolean;
  onClose: () => void;
  sessions: SessionSummary[];
  currentId: string | null;
  onPick: (id: string) => void;
};

export default function HistoryDialog({ open, onClose, sessions, currentId, onPick }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto w-[min(560px,92vw)] rounded-2xl border border-line bg-panel p-0 text-ink"
    >
      {open && (
        <div className="max-h-[80vh] overflow-y-auto p-5">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-base font-semibold">History</h2>
            <button onClick={onClose} className="text-sm text-mute hover:text-ink">
              Close
            </button>
          </div>
          <p className="mb-4 text-sm text-mute">Every chat is saved. Open one to replay it or carry on where it stopped.</p>
          {sessions.length === 0 && <p className="text-sm text-mute">No chats yet. Run something first.</p>}
          <ul className="space-y-2">
            {sessions.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => onPick(s.id)}
                  className={cx(
                    "flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition hover:bg-line/40",
                    s.id === currentId ? "border-accent" : "border-line",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{s.title || "Untitled chat"}</span>
                    <span className="block text-xs text-mute">
                      {new Date(s.updated * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} · {s.turns}{" "}
                      {s.turns === 1 ? "turn" : "turns"}
                      {s.interrupted_at && ` · stopped at ${s.interrupted_at.tool}`}
                    </span>
                  </span>
                  <Chip tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Chip>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </dialog>
  );
}
