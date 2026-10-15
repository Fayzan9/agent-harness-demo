"use client";

import { useCallback, useRef, useState } from "react";
import { compact as requestCompact, streamBranch, streamResume, streamRun } from "./api";
import type { HarnessEvent, RunConfig, SessionDetail, Turn } from "./types";

type Source = (signal: AbortSignal) => AsyncGenerator<HarnessEvent>;

/** One chat: a list of turns, each with its own events. New events stream into the last turn. */
export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [running, setRunning] = useState(false);
  const [queuedAt, setQueuedAt] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);

  const consume = useCallback(async (label: string, source: Source) => {
    setRunning(true);
    setQueuedAt(null);
    setTurns((t) => [...t, { runId: "", task: label, events: [] }]); // so the question shows straight away
    abort.current = new AbortController();
    const updateLast = (fn: (turn: Turn) => Turn) => setTurns((t) => t.map((x, i) => (i === t.length - 1 ? fn(x) : x)));
    try {
      for await (const e of source(abort.current.signal)) {
        if (e.type === "run_started") setSessionId(e.data.session_id);
        updateLast((x) => ({
          runId: e.type === "run_started" ? e.data.run_id : x.runId,
          task: e.type === "run_started" ? e.data.task : x.task,
          events: [...x.events, e],
        }));
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        const message = (err as Error).message;
        updateLast((x) => ({ ...x, events: [...x.events, { type: "error", step: 0, data: { message }, ts: Date.now() / 1000, agent: "main" }] }));
      }
    } finally {
      setRunning(false);
    }
  }, []);

  const start = useCallback((cfg: RunConfig) => consume(cfg.task, (s) => streamRun(cfg, sessionId, s)), [consume, sessionId]);

  const resume = useCallback(
    (cfg: RunConfig) => sessionId && consume("Resumed after an interruption", (s) => streamResume(sessionId, cfg, s)),
    [consume, sessionId],
  );

  const branch = useCallback(
    (runId: string, eventIndex: number, cfg: RunConfig) => {
      setSessionId(null);
      setTurns([]);
      return consume("Re-run from here", (s) => streamBranch(runId, eventIndex, cfg, s));
    },
    [consume],
  );

  const load = useCallback((detail: SessionDetail) => {
    setSessionId(detail.id);
    setTurns(detail.turns.map((t) => ({ runId: t.run_id, task: t.task, events: t.events })));
  }, []);

  /** Show a run that did not come from a chat, such as an eval run, as a single turn. */
  const loadEvents = useCallback((task: string, events: HarnessEvent[]) => {
    setSessionId(null);
    setTurns([{ runId: "", task, events }]);
  }, []);

  const newChat = useCallback(() => {
    setSessionId(null);
    setTurns([]);
  }, []);

  const stop = useCallback(() => abort.current?.abort(), []);

  const last = turns[turns.length - 1];
  const compactQueued =
    running && queuedAt !== null && !(last?.events.slice(queuedAt).some((e) => e.type === "compaction_started") ?? false);
  const compact = useCallback(() => {
    if (!last?.runId) return;
    setQueuedAt(last.events.length);
    requestCompact(last.runId);
  }, [last]);

  return { sessionId, turns, running, start, resume, branch, load, loadEvents, newChat, stop, compact, compactQueued };
}
