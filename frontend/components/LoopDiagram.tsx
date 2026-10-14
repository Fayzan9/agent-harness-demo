import type { ReactNode } from "react";
import type { StageTone, Stage } from "@/lib/derive";
import type { Usage } from "@/lib/types";
import { PARTS } from "./ContextBar";

type Kind = "accent" | "warn" | "plain";
const STAGES: { id: Stage; title: string; sub: string; kind: Kind }[] = [
  { id: "agent", title: "Agent", sub: "decides", kind: "accent" },
  { id: "hooksBefore", title: "Hooks", sub: "before", kind: "warn" },
  { id: "gate", title: "Gate", sub: "approve", kind: "warn" },
  { id: "tools", title: "Tools", sub: "runs", kind: "plain" },
  { id: "hooksAfter", title: "Hooks", sub: "after", kind: "warn" },
];

const W = 104;
const H = 52;
const GAP = 34;
const Y = 14;
const x = (i: number) => i * (W + GAP);
const MID = Y + H / 2;
const LANE_Y = Y + H + 66;

const STROKE: Record<Kind, string> = { accent: "var(--accent)", warn: "var(--warn)", plain: "var(--mute)" };
const SOFT: Record<Kind, string> = { accent: "var(--accent-soft)", warn: "var(--warn-soft)", plain: "var(--line)" };

// Straight links between neighbours, then the U-shaped return path back to the agent.
const LINKS = [0, 1, 2, 3].map((i) => `M ${x(i) + W} ${MID} H ${x(i + 1) - 3}`);
const RETURN = `M ${x(4) + W / 2} ${Y + H} V ${Y + H + 30} H ${x(0) + W / 2 + 22} V ${Y + H + 4}`;
const EDGE_OF: Partial<Record<Stage, string>> = {
  agent: LINKS[0],
  hooksBefore: LINKS[1],
  gate: LINKS[2],
  tools: LINKS[3],
  hooksAfter: RETURN,
  return: RETURN,
};

type Props = {
  stage?: Stage;
  tone: StageTone;
  waiting: boolean;
  helper: boolean;
  subUsage?: Usage;
  onStage: (stage: Stage) => void;
};

export default function LoopDiagram({ stage, tone, waiting, helper, subUsage, onStage }: Props) {
  const toneColor = { normal: undefined, warn: "var(--warn)", bad: "var(--bad)" }[tone];
  const toneSoft = { normal: undefined, warn: "var(--warn-soft)", bad: "var(--bad-soft)" }[tone];
  const dotPath = stage && !waiting ? EDGE_OF[stage] : undefined;
  const laneOn = stage === "helper";

  return (
    <svg viewBox={`0 0 ${x(4) + W} ${LANE_Y + 62}`} className="w-full" role="img" aria-label="The agent loop">
      <defs>
        {(["mute", "accent"] as const).map((c) => (
          <marker key={c} id={`head-${c}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M2 1L8 5L2 9" fill="none" stroke={`var(--${c})`} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </marker>
        ))}
      </defs>

      {LINKS.map((d, i) => (
        <path key={i} d={d} fill="none" stroke="var(--mute)" strokeWidth="1.5" markerEnd="url(#head-mute)" />
      ))}
      <path
        d={RETURN}
        fill="none"
        stroke={stage === "return" ? "var(--accent)" : "var(--mute)"}
        strokeWidth="1.5"
        strokeDasharray="5 4"
        markerEnd={`url(#head-${stage === "return" ? "accent" : "mute"})`}
      />
      <text x={(x(4) + W / 2 + x(0) + W / 2 + 22) / 2} y={Y + H + 52} textAnchor="middle" className="fill-mute" fontSize="12.5">
        result goes back into context
      </text>

      {STAGES.map((s, i) => {
        const on = stage === s.id;
        return (
          <g key={`${s.id}-${i}`} className="cursor-pointer" onClick={() => onStage(s.id)}>
            <rect
              x={x(i)}
              y={Y}
              width={W}
              height={H}
              rx="12"
              style={{
                fill: on ? (toneSoft ?? SOFT[s.kind]) : "var(--panel)",
                stroke: on ? (toneColor ?? STROKE[s.kind]) : "var(--line)",
                strokeWidth: on ? 2 : 1.25,
                transition: "all 0.25s",
              }}
            />
            <text x={x(i) + W / 2} y={Y + 23} textAnchor="middle" className="fill-ink" fontSize="15" fontWeight="600">
              {s.title}
            </text>
            <text x={x(i) + W / 2} y={Y + 40} textAnchor="middle" className="fill-mute" fontSize="12.5">
              {s.sub}
            </text>
          </g>
        );
      })}

      <line
        x1={x(0) + 22}
        y1={Y + H + 4}
        x2={x(0) + 22}
        y2={LANE_Y - 4}
        stroke={laneOn ? "var(--accent)" : "var(--mute)"}
        strokeWidth="1.5"
        markerStart={`url(#head-${laneOn ? "accent" : "mute"})`}
        markerEnd={`url(#head-${laneOn ? "accent" : "mute"})`}
      />

      <g className="cursor-pointer" onClick={() => onStage("helper")} opacity={helper ? 1 : 0.55}>
        <rect
          x="0"
          y={LANE_Y}
          width={x(4) + W}
          height="58"
          rx="12"
          fill="none"
          strokeDasharray={laneOn ? undefined : "5 4"}
          style={{ stroke: laneOn ? "var(--accent)" : "var(--line)", strokeWidth: laneOn ? 2 : 1.25 }}
        />
        <rect x="12" y={LANE_Y + 10} width="104" height="38" rx="9" style={{ fill: laneOn ? "var(--accent-soft)" : "var(--panel)", stroke: "var(--line)" }} />
        <text x="64" y={LANE_Y + 26} textAnchor="middle" className="fill-ink" fontSize="14" fontWeight="600">
          Helper
        </text>
        <text x="64" y={LANE_Y + 41} textAnchor="middle" className="fill-mute" fontSize="11.5">
          fresh context
        </text>
        <rect x="134" y={LANE_Y + 19} width="420" height="20" rx="6" style={{ fill: "var(--bg)", stroke: "var(--line)" }} />
        {subUsage &&
          PARTS.reduce<{ els: ReactNode[]; at: number }>(
            (acc, { key, color }) => {
              const w = ((subUsage.parts[key] ?? 0) / subUsage.limit) * 420;
              acc.els.push(<rect key={key} x={134 + acc.at} y={LANE_Y + 19} width={w} height="20" fill={color} />);
              acc.at += w;
              return acc;
            },
            { els: [], at: 0 },
          ).els}
        <text x="568" y={LANE_Y + 33} className="fill-mute" fontSize="12.5">
          {subUsage ? `${subUsage.total} / ${subUsage.limit}` : "helper context"}
        </text>
      </g>

      {dotPath && (
        <circle r="5" fill="var(--accent)">
          <animateMotion key={dotPath + stage} dur="0.9s" repeatCount="indefinite" path={dotPath} />
        </circle>
      )}
    </svg>
  );
}
