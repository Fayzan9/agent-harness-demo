"use client";

import type { View } from "@/lib/derive";
import { Button, Panel } from "./ui";

type Props = {
  view: View;
  input: string;
  setInput: (v: string) => void;
  running: boolean;
  decided: Record<string, boolean>;
  stepHint: boolean;
  onSend: () => void;
  onStop: () => void;
  onDecide: (callId: string, allow: boolean) => void;
};

export default function AskPanel({ view, input, setInput, running, decided, stepHint, onSend, onStop, onDecide }: Props) {
  const pending = view.pending;
  const callId = pending?.data.call_id as string | undefined;
  const choice = callId !== undefined ? decided[callId] : undefined;

  return (
    <Panel num={1} title="Ask" className="flex flex-col md:min-h-[430px]">
      <div className="flex flex-1 flex-col gap-3 text-sm">
        {!view.task && (
          <p className="my-auto text-center text-mute">
            {stepHint ? "Press Next below to reveal the run one event at a time." : "Pick a scenario at the top, or type your own task below."}
          </p>
        )}

        {view.task && (
          <div className="ml-8 self-end rounded-2xl rounded-br-md bg-accent-soft px-3.5 py-2.5 text-ink">{view.task}</div>
        )}

        {view.status === "running" && (
          <div className="flex items-center gap-2 text-mute">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            {view.activity}
          </div>
        )}

        {pending && (
          <div className="rounded-xl border border-warn/40 bg-warn-soft p-3">
            <p className="font-medium text-warn">{pending.data.tool} wants to run</p>
            <pre className="mt-1 overflow-x-auto font-mono text-xs text-ink">{JSON.stringify(pending.data.args, null, 2)}</pre>
            {choice === undefined ? (
              <div className="mt-3 flex gap-2">
                <Button variant="primary" onClick={() => onDecide(callId!, true)}>
                  Allow
                </Button>
                <Button onClick={() => onDecide(callId!, false)}>Deny</Button>
              </div>
            ) : (
              <p className="mt-2 text-xs text-mute">{choice ? "Allowed" : "Denied"}. The agent carries on (press Next if you are stepping).</p>
            )}
          </div>
        )}

        {view.answer !== undefined && (
          <div className="mr-8 self-start rounded-2xl rounded-bl-md border border-line px-3.5 py-2.5">{view.answer}</div>
        )}

        {view.error && (
          <div className="rounded-xl border border-bad/40 bg-bad-soft p-3 text-xs text-bad">{view.error}</div>
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
          placeholder="Ask the agent to do something"
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
