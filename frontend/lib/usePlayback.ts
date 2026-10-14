"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Decides how many of the run's events are visible. `null` means follow the run live. */
export function usePlayback(total: number, running: boolean) {
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const live = useRef({ total, running, cursor });
  useEffect(() => {
    live.current = { total, running, cursor };
  });

  const shown = cursor === null ? total : Math.min(cursor, total);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const { total, running, cursor } = live.current;
      const now = cursor ?? total;
      if (now >= total && !running) setPlaying(false);
      else setCursor(Math.min(total, now + 1));
    }, 700);
    return () => clearInterval(id);
  }, [playing]);

  const stepBack = useCallback(() => {
    setPlaying(false);
    setCursor((c) => Math.max(0, (c ?? live.current.total) - 1));
  }, []);

  return {
    shown,
    mode: cursor === null ? ("auto" as const) : ("step" as const),
    playing,
    setMode: (mode: "auto" | "step") => {
      setPlaying(false);
      setCursor(mode === "auto" ? null : shown);
    },
    next: () => setCursor((c) => Math.min(live.current.total, (c ?? live.current.total) + 1)),
    back: stepBack,
    scrub: (i: number) => {
      setPlaying(false);
      setCursor(i);
    },
    togglePlay: () => {
      setCursor((c) => (c === null ? live.current.total : c));
      setPlaying((p) => !p);
    },
    /** Called when a new run starts. Step mode starts with nothing revealed. */
    reset: () => {
      setPlaying(false);
      setCursor((c) => (c === null ? null : 0));
    },
  };
}
