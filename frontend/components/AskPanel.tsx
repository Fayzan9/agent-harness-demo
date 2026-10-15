"use client";

import { derive, type View } from "@/lib/derive";
import type { InterruptedAt, Turn } from "@/lib/types";
import { Button, Panel, cx } from "./ui";

type Props = {
  turns: Turn[];
  selected: number; // the turn shown in Watch and Inspect
  onSelect: (i: number) => void;
  view: View; // the selected turn, at the replay position
  input: string;
  setInput: (v: string) => void;
  running: boolean;
  decided: Record<string, boolean>;
  stepHint: boolean;
  interrupted: { at: InterruptedAt | null } | null;
  onSend: () => void;
  onStop: () => void;
  onDecide: (callId: string, allow: boolean) => void;
  onResume: () => void;
  onNewChat: () => void;
};

const STATE_TEXT: Record<string, string> = {
  awaiting_approval: "waiting for your approval",
  running: "running",
  "not started": "about to run",
};

export default function AskPanel({
  turns,
  selected,
  onSelect,
  view,
  input,
  setInput,
  running,
  decided,
  stepHint,
  interrupted,
  onSend,
  onStop,
  onDecide,
  onResume,
  onNewChat,
}: Props) {
  return (
    <Panel
      num={1}
      title="Ask"
      className="flex flex-col md:min-h-[430px]"
      right={
        <Button className="!px-2 !py-0.5 !text-xs" onClick={onNewChat} disabled={running || turns.length === 0}>
          New chat
        </Button>
      }
    >
      <div className="flex flex-1 flex-col gap-3 text-sm">
        {turns.length === 0 && (
          <p className="my-auto text-center text-mute">Pick a scenario at the top, or type your own task below.</p>
        )}

        {turns.map((turn, i) => {
          const isSel = i === selected;
          const v = isSel ? view : derive(turn.events);
          const live = isSel && running && i === turns.length - 1;
          const pending = live ? v.pending : undefined;
          const callId = pending?.data.call_id as string | undefined;
          const choice = callId !== undefined ? decided[callId] : undefined;
          return (
            <div key={i} className="flex flex-col gap-3">
              <button
                onClick={() => onSelect(i)}
                title={turns.length > 1 ? "Show this turn in Watch and Inspect" : undefined}
                className={cx(
                  "ml-8 self-end rounded-2xl rounded-br-md bg-accent-soft px-3.5 py-2.5 text-left text-ink transition",
                  turns.length > 1 && isSel && "ring-2 ring-accent/40",
                )}
              >
                {turn.task}
              </button>

              {isSel && stepHint && (
                <p className="text-center text-xs text-mute">Press Next below to reveal the run one event at a time.</p>
              )}

              {live && v.status === "running" && (
                <div className="flex items-center gap-2 text-mute">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                  {v.activity || "Starting"}
                </div>
              )}

              {pending && (
                <div className="rounded-xl border border-warn/40 bg-warn-soft p-3">
                  <p className="font-medium text-warn">{pending.data.tool} wants to run</p>
                  {pending.data.maybe_ran && (
                    <p className="mt-1 text-xs text-warn">
                      It was already running when the chat stopped, so it may have taken effect. Check before you allow it again.
                    </p>
                  )}
                  <pre className="mt-1 overflow-x-auto font-mono text-xs text-ink">{JSON.stringify(pending.data.args, null, 2)}</pre>
                  {choice === undefined ? (
                    <div className="mt-3 flex gap-2">
                      <Button variant="primary" onClick={() => onDecide(callId!, true)}>
                        Allow
                      </Button>
                      <Button onClick={() => onDecide(callId!, false)}>Deny</Button>
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-mute">
                      {choice ? "Allowed" : "Denied"}. The agent carries on (press Next if you are stepping).
                    </p>
                  )}
                </div>
              )}

              {v.answer !== undefined && (
                <div className="mr-8 self-start rounded-2xl rounded-bl-md border border-line px-3.5 py-2.5">{v.answer}</div>
              )}

              {v.error && <div className="rounded-xl border border-bad/40 bg-bad-soft p-3 text-xs text-bad">{v.error}</div>}
            </div>
          );
        })}

        {interrupted && !running && (
          <div className="rounded-xl border border-warn/40 bg-warn-soft p-3">
            <p className="font-medium text-warn">This chat stopped part-way</p>
            <p className="mt-1 text-xs text-ink">
              {interrupted.at
                ? `${interrupted.at.tool} was ${STATE_TEXT[interrupted.at.state] ?? interrupted.at.state} when it stopped.`
                : "It stopped between steps."}{" "}
              Resuming continues from the last saved checkpoint.
              {interrupted.at?.state === "running" && " That call may already have taken effect, so you will be asked before it runs again."}
            </p>
            <Button variant="primary" className="mt-3" onClick={onResume}>
              Resume
            </Button>
          </div>
        )}
      </div>

      <form
        className="mt-4 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!running && input.trim()) onSend();
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!running && input.trim()) onSend();
            }
          }}
          rows={2}
          placeholder={turns.length ? "Ask a follow-up" : "Ask the agent to do something"}
          className="min-h-[44px] flex-1 resize-none rounded-xl border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
        />
        {running ? (
          <Button type="button" variant="danger" onClick={onStop}>
            Stop
          </Button>
        ) : (
          <Button type="submit" variant="primary" disabled={!input.trim()}>
            Send
          </Button>
        )}
      </form>
    </Panel>
  );
}
