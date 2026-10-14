import type { Stage, View } from "@/lib/derive";
import ContextBar from "./ContextBar";
import LoopDiagram from "./LoopDiagram";
import { Panel } from "./ui";

type Props = {
  view: View;
  threshold: number;
  running: boolean;
  compactQueued: boolean;
  onCompact: () => void;
  onStage: (stage: Stage) => void;
  onSegment: (key: string) => void;
};

export default function WatchPanel({ view, threshold, running, compactQueued, onCompact, onStage, onSegment }: Props) {
  return (
    <Panel num={2} title="Watch" hint="Click any box to configure it">
      <div className="flex flex-col gap-6">
        <ContextBar
          usage={view.usage}
          threshold={threshold}
          flash={view.compacting}
          canCompact={running}
          queued={compactQueued}
          onCompact={onCompact}
          onSegment={onSegment}
        />
        <div className="overflow-x-auto">
          <div className="min-w-[600px]">
            <LoopDiagram
              stage={view.stage}
              tone={view.tone}
              waiting={view.status === "waiting"}
              helper={view.helper}
              subUsage={view.subUsage}
              onStage={onStage}
            />
          </div>
        </div>
      </div>
    </Panel>
  );
}
