"use client";

import { useCallback, useRef, useState } from "react";
import { compact as requestCompact, streamRun } from "./api";
import type { HarnessEvent, RunConfig } from "./types";

/** Starts a run and turns the event stream into React state. */
export function useRun() {
  const [events, setEvents] = useState<HarnessEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [queuedAt, setQueuedAt] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);

  const start = useCallback(async (cfg: RunConfig) => {
    setEvents([]);
    setQueuedAt(null);
    setRunning(true);
    abort.current = new AbortController();
    try {
      for await (const e of streamRun(cfg, abort.current.signal)) {
        setEvents((prev) => [...prev, e]);
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        const message = String(err);
        setEvents((prev) => [...prev, { type: "error", step: 0, data: { message }, ts: Date.now() / 1000, agent: "main" }]);
      }
    } finally {
      setRunning(false);
    }
  }, []);

  const stop = useCallback(() => abort.current?.abort(), []);

  const runId = events[0]?.data.run_id as string | undefined;
  // The loop only compacts at the start of its next pass, so show "queued" until it does.
  const compactQueued = running && queuedAt !== null && !events.slice(queuedAt).some((e) => e.type === "compaction_started");
  const compact = useCallback(() => {
    if (!runId) return;
    setQueuedAt(events.length);
    requestCompact(runId);
  }, [runId, events.length]);

  return { events, running, start, stop, compact, compactQueued };
}
