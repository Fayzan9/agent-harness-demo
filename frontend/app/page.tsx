"use client";

import { useEffect, useMemo, useState } from "react";
import AskPanel from "@/components/AskPanel";
import ConfigDialog, { type Target } from "@/components/ConfigDialog";
import EvalsView from "@/components/EvalsView";
import HistoryDialog from "@/components/HistoryDialog";
import InspectPanel, { type Tab } from "@/components/InspectPanel";
import ReplayBar from "@/components/ReplayBar";
import TopBar from "@/components/TopBar";
import WatchPanel from "@/components/WatchPanel";
import { approve, getOptions, getSession, getSessions, getWorkspace, resetWorkspace } from "@/lib/api";
import { derive } from "@/lib/derive";
import { CUSTOM_ID, SCENARIOS } from "@/lib/scenarios";
import type { HarnessEvent, Options, SessionSummary, Setup, WorkspaceFile } from "@/lib/types";
import { usePlayback } from "@/lib/usePlayback";
import { useSession } from "@/lib/useSession";

export default function Home() {
  const [options, setOptions] = useState<Options | null>(null);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [history, setHistory] = useState<SessionSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [setup, setSetup] = useState<Setup>(SCENARIOS[0].setup);
  const [input, setInput] = useState(SCENARIOS[0].task);
  const [tab, setTab] = useState<Tab>("events");
  const [focusPart, setFocusPart] = useState<string>();
  const [target, setTarget] = useState<Target | null>(null);
  const [decided, setDecided] = useState<Record<string, boolean>>({});
  const [picked, setPicked] = useState<number | null>(null); // null means follow the newest turn
  const [screen, setScreen] = useState<"play" | "evals">("play");

  const chat = useSession();
  const selected = picked ?? Math.max(chat.turns.length - 1, 0);
  const turn = chat.turns[selected];
  const events = useMemo(() => turn?.events ?? [], [turn]);
  const live = chat.running && selected === chat.turns.length - 1;

  const playback = usePlayback(events.length, live);
  const viewed = useMemo(() => events.slice(0, playback.shown), [events, playback.shown]);
  const view = useMemo(() => derive(viewed), [viewed]);

  useEffect(() => {
    getOptions().then(setOptions).catch(() => setOptions(null));
  }, []);

  // Refresh the file list and the history whenever a run ends, and once on load.
  useEffect(() => {
    if (chat.running) return;
    getWorkspace().then(setFiles).catch(() => setFiles([]));
    getSessions().then(setHistory).catch(() => setHistory([]));
  }, [chat.running]);

  const current = history.find((h) => h.id === chat.sessionId);
  const interrupted = !chat.running && current?.status === "interrupted" ? { at: current.interrupted_at } : null;

  const changeSetup = (s: Setup) => {
    setSetup(s);
    setScenarioId(CUSTOM_ID);
  };

  const newChat = () => {
    chat.newChat();
    setPicked(null);
    setDecided({});
    playback.setMode("auto");
  };

  const pickScenario = (id: string) => {
    const s = SCENARIOS.find((x) => x.id === id);
    if (!s) return;
    setScenarioId(id);
    setSetup(s.setup);
    setInput(s.task);
    newChat();
  };

  const startTurn = () => {
    setDecided({});
    setTab("events");
    setPicked(null);
    playback.reset();
  };

  const send = async () => {
    const firstMessage = chat.turns.length === 0;
    if (firstMessage) await resetWorkspace().catch(() => undefined); // a fresh chat starts from the demo files
    startTurn();
    chat.start({ ...setup, task: input });
    if (!firstMessage) setInput("");
  };

  const resume = () => {
    startTurn();
    chat.resume({ ...setup, task: "" });
  };

  const rerunFrom = (eventIndex: number) => {
    if (!turn?.runId) return;
    startTurn();
    chat.branch(turn.runId, eventIndex, { ...setup, task: "" });
  };

  const openChat = async (id: string) => {
    const detail = await getSession(id);
    chat.load(detail);
    if (detail.setup) changeSetup({ ...setup, ...detail.setup }); // reopen with the settings that chat used
    setPicked(null);
    setDecided({});
    playback.setMode("auto");
    setHistoryOpen(false);
  };

  const decide = (callId: string, allow: boolean) => {
    setDecided((d) => ({ ...d, [callId]: allow }));
    approve(callId, allow);
  };

  const replayEvalRun = (task: string, runEvents: HarnessEvent[]) => {
    chat.loadEvents(task, runEvents);
    setPicked(null);
    setDecided({});
    playback.setMode("auto");
    setTab("events");
    setScreen("play");
  };

  const selectTurn = (i: number) => {
    setPicked(i);
    playback.setMode("auto");
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
        onHistory={() => setHistoryOpen(true)}
        view={screen}
        onView={setScreen}
        status={view.status}
        stats={view.stats}
      />

      <div className={screen === "play" ? "contents" : "hidden"}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[320px_minmax(0,1fr)]">
          <AskPanel
            turns={chat.turns}
            selected={selected}
            onSelect={selectTurn}
            view={view}
            input={input}
            setInput={setInput}
            running={chat.running}
            decided={decided}
            stepHint={events.length > 0 && playback.shown === 0}
            interrupted={interrupted}
            onSend={send}
            onStop={chat.stop}
            onDecide={decide}
            onResume={resume}
            onNewChat={newChat}
          />
          <WatchPanel
            view={view}
            threshold={setup.compact_at}
            running={live}
            compactQueued={chat.compactQueued}
            onCompact={chat.compact}
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
          canBranch={!chat.running && !!turn?.runId}
          onBranch={rerunFrom}
        />

        <ReplayBar
          shown={playback.shown}
          total={events.length}
          mode={playback.mode}
          playing={playback.playing}
          onBack={playback.back}
          onNext={playback.next}
          onPlay={playback.togglePlay}
          onScrub={playback.scrub}
        />

      </div>

      <div className={screen === "evals" ? "" : "hidden"}>
        <EvalsView onReplay={replayEvalRun} />
      </div>

      <ConfigDialog target={target} onClose={() => setTarget(null)} options={options} setup={setup} setSetup={changeSetup} />
      <HistoryDialog
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={history}
        currentId={chat.sessionId}
        onPick={openChat}
      />
    </main>
  );
}
