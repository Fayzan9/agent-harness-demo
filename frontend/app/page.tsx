"use client";

import { useEffect, useMemo, useState } from "react";
import AskPanel from "@/components/AskPanel";
import ConfigDialog, { type Target } from "@/components/ConfigDialog";
import InspectPanel, { type Tab } from "@/components/InspectPanel";
import ReplayBar from "@/components/ReplayBar";
import TopBar from "@/components/TopBar";
import WatchPanel from "@/components/WatchPanel";
import { approve, getOptions, getWorkspace, resetWorkspace } from "@/lib/api";
import { derive } from "@/lib/derive";
import { CUSTOM_ID, SCENARIOS } from "@/lib/scenarios";
import type { Options, Setup, WorkspaceFile } from "@/lib/types";
import { usePlayback } from "@/lib/usePlayback";
import { useRun } from "@/lib/useRun";

export default function Home() {
  const [options, setOptions] = useState<Options | null>(null);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [setup, setSetup] = useState<Setup>(SCENARIOS[0].setup);
  const [input, setInput] = useState(SCENARIOS[0].task);
  const [tab, setTab] = useState<Tab>("events");
  const [focusPart, setFocusPart] = useState<string>();
  const [target, setTarget] = useState<Target | null>(null);
  const [decided, setDecided] = useState<Record<string, boolean>>({});

  const run = useRun();
  const playback = usePlayback(run.events.length, run.running);
  const viewed = useMemo(() => run.events.slice(0, playback.shown), [run.events, playback.shown]);
  const view = useMemo(() => derive(viewed), [viewed]);

  useEffect(() => {
    getOptions().then(setOptions).catch(() => setOptions(null));
  }, []);

  // Refresh the file list whenever a run ends, and once on load.
  useEffect(() => {
    if (!run.running) getWorkspace().then(setFiles).catch(() => setFiles([]));
  }, [run.running]);

  const changeSetup = (s: Setup) => {
    setSetup(s);
    setScenarioId(CUSTOM_ID);
  };

  const pickScenario = (id: string) => {
    const s = SCENARIOS.find((x) => x.id === id);
    if (!s) return;
    setScenarioId(id);
    setSetup(s.setup);
    setInput(s.task);
  };

  const send = async () => {
    await resetWorkspace().catch(() => undefined); // puts the demo files back as they were
    setDecided({});
    setTab("events");
    playback.reset();
    run.start({ ...setup, task: input });
  };

  const decide = (callId: string, allow: boolean) => {
    setDecided((d) => ({ ...d, [callId]: allow }));
    approve(callId, allow);
  };

  const pickSegment = (key: string) => {
    setFocusPart(key);
    setTab(key === "memory" ? "memory" : "context");
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1200px] flex-col gap-4 p-4 md:p-6">
      <TopBar
        scenarios={SCENARIOS}
        scenarioId={scenarioId}
        onScenario={pickScenario}
        mode={playback.mode}
        onMode={playback.setMode}
        onSettings={() => setTarget("settings")}
        status={view.status}
        stats={view.stats}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[320px_minmax(0,1fr)]">
        <AskPanel
          view={view}
          input={input}
          setInput={setInput}
          running={run.running}
          decided={decided}
          stepHint={run.events.length > 0 && playback.shown === 0}
          onSend={send}
          onStop={run.stop}
          onDecide={decide}
        />
        <WatchPanel
          view={view}
          threshold={setup.compact_at}
          running={run.running}
          compactQueued={run.compactQueued}
          onCompact={run.compact}
          onStage={setTarget}
          onSegment={pickSegment}
        />
      </div>

      <InspectPanel
        tab={tab}
        setTab={setTab}
        events={viewed}
        view={view}
        memory={setup.memory}
        setMemory={(memory) => changeSetup({ ...setup, memory })}
        files={files}
        focusPart={focusPart}
      />

      <ReplayBar
        shown={playback.shown}
        total={run.events.length}
        mode={playback.mode}
        playing={playback.playing}
        onBack={playback.back}
        onNext={playback.next}
        onPlay={playback.togglePlay}
        onScrub={playback.scrub}
      />

      <ConfigDialog target={target} onClose={() => setTarget(null)} options={options} setup={setup} setSetup={changeSetup} />
    </main>
  );
}
