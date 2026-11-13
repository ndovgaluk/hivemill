// The arrows: drawn on a fixed SVG layer inside React Flow's viewport (layout is fixed, so no handle measuring),
// with a clickable label chip per arrow. The selected event's arrow animates in its direction.
import { useId } from "react";

import { Dir, EdgeId, SelectionKind, Severity, type NodeId } from "../constants";
import { fmtDuration } from "../format";
import { useSelection } from "../selection";
import type { FlowData, FlowEdge } from "../types";
import styles from "./diagram.module.css";
import { groupOf, nodeLabel } from "../groups";
import { BUS_BRANCHES, BUS_LABEL, CANVAS_H, CANVAS_W, EDGES, FRAMES, toPath } from "./layout";

const FLOW_FORWARD = "forward";
const HEAD_ACCENT = "accent";   // the selected arrow's head when its severity is ok
const HEADS = [Severity.Ok, Severity.Warn, Severity.Bad, HEAD_ACCENT] as const;
const FLOW_REVERSE = "reverse";

function labelOf(e: FlowEdge): string {
  if (e.wait_s !== null) return fmtDuration(e.wait_s);
  const { forward, back } = e.counts;
  if (forward || back) return back ? `${forward}→ ${back}←` : `${forward}→`;
  return e.label;
}

export function Edges({ data, motion, onOpenInstructions }: {
  data: FlowData;
  motion: boolean;
  onOpenInstructions: (edgeId: string) => void;
}) {
  const sel = useSelection();
  const event = sel.selection?.kind === SelectionKind.Event ? data.events.find((e) => e.id === sel.selection?.id) : undefined;
  const dim = sel.selection !== null;
  const pickedId = sel.selection?.kind === SelectionKind.Edge ? sel.selection.id : null;
  // the selected arrow glows (and its dashes march, unless reduced motion is on)
  const glow = (id: string) => (id === pickedId ? `${styles.picked} ${motion ? styles.glow : ""}` : "");
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");   // React ids hold characters a url(#…) reference may not
  const headId = (k: string) => `flow-head-${uid}-${k}`;
  // arrowheads point at the receiver; an arrow with traffic back also gets one at its start
  const heads = (e: FlowEdge) => {
    const k = e.id === pickedId && e.severity === Severity.Ok ? HEAD_ACCENT : e.severity;
    return { markerEnd: `url(#${headId(k)})`, markerStart: e.counts.back > 0 ? `url(#${headId(k)})` : undefined };
  };
  const instructions = new Set(data.events.filter((e) => e.is_instruction && e.edge).map((e) => e.edge));

  const click = (e: FlowEdge) => {
    sel.select({ kind: SelectionKind.Edge, id: e.id });
    if (instructions.has(e.id)) onOpenInstructions(e.id);
  };

  return (
    <>
      {/* HM-17: a dashed frame around boxes that act as one step, labelled on its top border; not clickable */}
      {(data.groups ?? []).map((g) => {
        const f = FRAMES[g.id];
        return f ? (
          <div key={g.id} className={styles.frame} style={{ left: f.x, top: f.y, width: f.w, height: f.h }}
               data-testid={`flow-group-${g.id}`} aria-hidden="true">
            <span className={styles.frameLabel}>{g.label}</span>
          </div>
        ) : null;
      })}
      <svg className={styles.edges} width={CANVAS_W} height={CANVAS_H} aria-hidden="true">
        <defs>
          {HEADS.map((k) => (
            <marker key={k} id={headId(k)} className={`${styles.head} ${styles[`head_${k}`] ?? ""}`} data-head={k}
                    viewBox="0 0 10 10" refX="10" refY="5" markerWidth="4.5" markerHeight="4.5" markerUnits="strokeWidth"
                    orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" />
            </marker>
          ))}
        </defs>
        {data.edges.flatMap((e) => {
          const active = event?.edge === e.id;
          const flow = active ? (event?.dir === Dir.Back ? FLOW_REVERSE : FLOW_FORWARD) : undefined;
          const hot = sel.hot.edges.has(e.id);
          const cls = `${styles.edge} ${styles[e.severity] ?? ""} ${e.pending ? styles.pendingEdge : ""} ${dim && !hot ? styles.dimEdge : ""}`;
          if (e.id === EdgeId.Bus) {
            // a box in a group (Reviewer, QA) has its branch on the group's frame
            const worker = [event?.from_node, event?.to_node].map((n) => (n ? groupOf(data, n) ?? n : n))
              .find((n) => n && n in BUS_BRANCHES) as NodeId | undefined;
            return Object.entries(BUS_BRANCHES).map(([node, pts]) => {
              const on = active && node === worker;
              return <path key={`${e.id}-${node}`} d={toPath(pts!)} {...heads(e)} className={`${cls} ${on && motion ? styles.animated : ""} ${glow(e.id)}`}
                           data-picked={e.id === pickedId}
                           data-testid={`flow-edge-path-${e.id}-${node}`} data-flow={on ? flow : undefined} />;
            });
          }
          const geo = EDGES[e.id as keyof typeof EDGES];
          return geo ? [<path key={e.id} d={toPath(geo.points)} {...heads(e)} className={`${cls} ${active && motion ? styles.animated : ""} ${glow(e.id)}`}
                              data-picked={e.id === pickedId}
                              data-testid={`flow-edge-path-${e.id}`} data-flow={flow} />] : [];
        })}
      </svg>
      {data.edges.map((e) => {
        const at = e.id === EdgeId.Bus ? BUS_LABEL : EDGES[e.id as keyof typeof EDGES]?.label;
        if (!at) return null;
        const active = event?.edge === e.id;
        return (
          <button key={e.id} type="button" className={`${styles.chip} ${styles[e.severity] ?? ""} ${e.id === pickedId && motion ? styles.glowBox : ""}`}
                  style={{ left: at[0], top: at[1] }}
                  data-testid={`flow-edge-${e.id}`} data-severity={e.severity} data-pending={e.pending}
                  data-flow={active ? (event?.dir === Dir.Back ? FLOW_REVERSE : FLOW_FORWARD) : undefined}
                  aria-pressed={sel.selection?.kind === SelectionKind.Edge && sel.selection.id === e.id}
                  aria-label={`${nodeLabel(data, e.from)} to ${e.to.map((t) => nodeLabel(data, t)).join(", ")}: ${labelOf(e)}`}
                  onClick={() => click(e)}>
            {labelOf(e)}
          </button>
        );
      })}
    </>
  );
}
