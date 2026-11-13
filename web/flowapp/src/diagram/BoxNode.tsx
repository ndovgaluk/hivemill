// One box of the diagram: a role or stage with its work time and cost (lens decides which is the main value).
import type { Node, NodeProps } from "@xyflow/react";

import { Lens, NodeId, NodeState, SelectionKind } from "../constants";
import { fmtCost, fmtDuration } from "../format";
import { useSelection } from "../selection";
import type { FlowNode } from "../types";
import styles from "./diagram.module.css";

export interface BoxData extends Record<string, unknown> {
  node: FlowNode;
  share: number | null;
  top: boolean;
  findings: number;
  severe: boolean;
  motion: boolean;
  onOpenFindings: (id: string) => void;
  onExpandLanes: (id: string) => void;
  onOpenEvents: (id: string) => void;
}

export const MSGS_ONLY = "msgs only";
export const NO_SESSIONS = "no sessions";
export const WAITED_TOTAL = "waited in total";
export const NOT_WAITING = "agents running";   // the Waiting box while somebody works, or the goal is closed
export const MESSAGE_ONLY = new Set<string>([NodeId.Boss, NodeId.Director, NodeId.System]);

const NEW_TAB = "_blank";
const NEW_TAB_REL = "noopener noreferrer";
const EXPAND_LABEL = "Expand on timeline";
const EVENTS_LABEL = "Messages and events";

export const BOX = "box";   // React Flow node type of every box
export type BoxNodeType = Node<BoxData, typeof BOX>;

const STATE_CLASS: Record<NodeState, string | undefined> = {
  [NodeState.Done]: styles.done,
  [NodeState.Live]: styles.live,
  [NodeState.Fail]: styles.fail,
  [NodeState.Idle]: styles.idle,
  [NodeState.Pending]: styles.pending,
};

export function BoxNode({ data }: NodeProps<BoxNodeType>) {
  const { node, share, top, findings, severe, motion } = data;
  const sel = useSelection();
  const selected = sel.selection?.kind === SelectionKind.Node && sel.selection.id === node.id;
  const dim = sel.selection !== null && !sel.hot.nodes.has(node.id);
  const pulse = sel.hot.sender === node.id;
  const time = fmtDuration(node.work_s);
  const cost = fmtCost(node.cost);
  let [main, second] = sel.lens === Lens.Cost ? [cost, time] : [time, cost];
  if (node.id === NodeId.Wait) {
    // the Waiting box: how long nobody has been running, and what for; no cost, whatever the lens
    // waiting now: this wait and what for; otherwise every wait so far
    [main, second] = node.state === NodeState.Live ? [fmtDuration(node.current_s ?? node.work_s), node.note ?? ""]
      : node.work_s ? [time, WAITED_TOTAL] : ["", NOT_WAITING];
  } else if (!node.agents.length && node.work_s === null && node.cost === null) {
    // no sessions at all: say why the figures are empty instead of "unknown unknown"
    [main, second] = ["", MESSAGE_ONLY.has(node.id) ? MSGS_ONLY : node.id === NodeId.Main ? "" : NO_SESSIONS];
  }
  return (
    <div className={styles.box} data-testid={`flow-node-${node.id}`} data-dim={dim} data-top={top} data-pulse={pulse}
         data-state={node.state}>
      <button
        type="button"
        className={`${styles.boxButton} ${selected ? styles.selected : ""} ${selected && motion ? styles.glowBox : pulse && motion ? styles.animated : node.state === NodeState.Live && !selected && !pulse ? styles.liveBox : ""}`}
        aria-label={node.label}
        title={node.id === NodeId.Wait && node.work_s !== null ? `${node.note ? `${node.note} · ` : ""}${time} ${WAITED_TOTAL}` : undefined}
        aria-pressed={selected}
        onClick={() => sel.select({ kind: SelectionKind.Node, id: node.id })}
      >
        <span className={styles.boxHead}>
          <span className={`${styles.dot} ${STATE_CLASS[node.state] ?? ""} ${node.state === NodeState.Live && motion ? styles.animated : ""}`} />
          <span className={styles.name}>{node.label}</span>
          {node.state === NodeState.Live ? (
            // working now: a small turning cog in the top right corner
            <svg className={`${styles.cog} ${styles.spin}`} data-testid={`flow-node-working-${node.id}`} aria-hidden="true"
                 width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor">
              <circle cx="7" cy="7" r="4.6" strokeWidth="2.6" strokeDasharray="1.806 1.806" />
              <circle cx="7" cy="7" r="3.1" strokeWidth="1.6" />
            </svg>
          ) : null}
        </span>
        <span className={styles.values}>
          <span className={styles.main} data-value="main">{main}</span>
          <span className={styles.second} data-value="second">{second}</span>
        </span>
        <span className={`${styles.bar} ${node.state === NodeState.Fail ? styles.barBad : sel.lens === Lens.Cost ? styles.barCost : ""}`} aria-hidden="true"
              data-share={share ?? 0} style={{ width: `${Math.round((share ?? 0) * 100)}%` }} />
      </button>
      {findings > 0 ? (
        <button type="button" className={`${styles.badge} ${severe ? styles.badgeBad : ""} ${severe && motion ? styles.animated : ""}`}
                aria-label={`${findings} finding${findings === 1 ? "" : "s"} on ${node.label}`}
                onClick={() => data.onOpenFindings(node.id)}>
          {findings}
        </button>
      ) : null}
      {node.links?.length ? (
        // outside the button (an anchor cannot sit in one), under the box; nodrag/nopan keep React Flow off the click
        <span className={`${styles.links} nodrag nopan`}>
          {node.links.map((l) => (
            <a key={l.url} className={styles.linkChip} href={l.url} target={NEW_TAB} rel={NEW_TAB_REL} title={l.url}>{l.label} ↗</a>
          ))}
        </span>
      ) : null}
      {selected ? (
        <span className={styles.toolbar}>
          <button type="button" aria-label={EXPAND_LABEL} title={EXPAND_LABEL} onClick={() => data.onExpandLanes(node.id)}>
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M2 3.5h10M2 7h6M2 10.5h8" /></svg>
          </button>
          <button type="button" aria-label={EVENTS_LABEL} title={EVENTS_LABEL} onClick={() => data.onOpenEvents(node.id)}>
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M2 2.5h10v7H6.5l-3 2.5V9.5H2z" /></svg>
          </button>
        </span>
      ) : null}
    </div>
  );
}
