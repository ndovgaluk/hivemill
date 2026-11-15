// The diagram region: React Flow for pan and zoom, custom boxes, our own fixed arrows, lens and zoom controls.
import { ReactFlow, ReactFlowProvider, ViewportPortal, useReactFlow } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { COPY_KEY, Lens, Severity } from "../constants";
import { CopyReference, RefChip } from "../reference/CopyReference";
import { buildReference, copyText, selParam } from "../reference/reference";
import { useReducedMotion } from "../useReducedMotion";
import { useSelection } from "../selection";
import type { FlowData } from "../types";
import { BOX, BoxNode, type BoxNodeType } from "./BoxNode";
import styles from "./diagram.module.css";
import { Edges } from "./Edges";
import { geometryOf } from "./geometry";
import { DEFAULT_ZOOM, NODE_H, NODE_W, ZOOM_STEPS } from "./layout";
import { WorkflowLine, Children } from "./Workflow";

export interface DiagramHandlers {
  onOpenFindings?: (nodeId: string) => void;
  onExpandLanes?: (nodeId: string) => void;
  onOpenEvents?: (nodeId: string) => void;
  onOpenInstructions?: (edgeId: string) => void;
}

const NODE_TYPES = { [BOX]: BoxNode };
const PRO_OPTIONS = { hideAttribution: true };
const noop = () => {};
const CANVAS_ROOM = 16;
const FIT_PAD = 24;        // px kept free right of the fitted diagram
const ZOOM_EPS = 0.001;   // under an engine layout's lowest arrow, as the old canvas keeps under its rework label
const LEGEND_TIME = "Box = work time, cost";
const LEGEND_COST = "Box = cost, share bar";
const LEGEND_ARROWS = "Arrow label = wait. Thicker, red = slower";
export const FLOW_HINT = "Select a box, a badge or a timeline mark. Click an arrow label to read the instructions sent over that link. Ctrl + wheel zooms.";

export function Diagram(props: { data: FlowData } & DiagramHandlers) {
  return (
    <ReactFlowProvider>
      <DiagramInner {...props} />
    </ReactFlowProvider>
  );
}

function DiagramInner({ data, onOpenFindings = noop, onExpandLanes = noop, onOpenEvents = noop, onOpenInstructions = noop }:
  { data: FlowData } & DiagramHandlers) {
  const sel = useSelection();
  const reduce = useReducedMotion();
  const motion = !reduce;
  const rf = useReactFlow();
  const [zoom, setZoom] = useState<number>(DEFAULT_ZOOM);

  const geo = useMemo(() => geometryOf(data), [data]);
  const nodes = useMemo<BoxNodeType[]>(() => {
    const cost = sel.lens === Lens.Cost;
    const total = cost ? data.totals.cost : data.elapsed_s;
    const known = data.nodes.filter((n) => n.cost !== null);
    const topId = cost && known.length ? known.reduce((a, b) => ((b.cost ?? 0) > (a.cost ?? 0) ? b : a)).id : null;
    // a node this bundle has no place for (a newer server) is left out instead of breaking the page
    return data.nodes.filter((n) => geo.boxes[n.id]).map((n) => {
      const mine = data.findings.filter((f) => f.node === n.id);
      const value = cost ? n.cost : n.work_s;
      return {
        id: n.id,
        type: BOX,
        position: geo.boxes[n.id]!,
        width: NODE_W,
        height: NODE_H,
        draggable: false,
        selectable: false,
        data: {
          node: n,
          share: value !== null && total ? Math.min(1, value / total) : null,
          top: n.id === topId,
          findings: mine.length,
          severe: mine.some((f) => f.severity === Severity.Bad),
          motion,
          onOpenFindings,
          onExpandLanes,
          onOpenEvents,
        },
      };
    });
  }, [data, geo, sel.lens, motion, onOpenFindings, onExpandLanes, onOpenEvents]);

  // HM-50: the zoom at which the whole diagram width fits the canvas; never above 100 %, never below the smallest step.
  // Unknown width (not laid out yet, or a test DOM): 100 %.
  const canvasRef = useRef<HTMLDivElement>(null);
  const canvasW = geo.canvas.w;
  const fitZoom = useCallback(() => {
    const w = canvasRef.current?.clientWidth ?? 0;
    return w > 0 ? Math.max(ZOOM_STEPS[0], Math.min(DEFAULT_ZOOM, (w - FIT_PAD) / canvasW)) : DEFAULT_ZOOM;
  }, [canvasW]);
  const ready = useRef(false);
  const fit = useCallback(() => {
    const z = fitZoom();
    setZoom(z);
    void rf.setViewport({ x: 0, y: 0, zoom: z });
  }, [fitZoom, rf]);
  // fit when the diagram is first drawn and when another workflow's (wider or narrower) diagram arrives, not on each poll
  useEffect(() => {
    if (ready.current) fit();
  }, [fit]);
  const step = (dir: 1 | -1) => {
    // the next allowed step above or below the current zoom, which may be a fitted value between two steps
    const next = dir > 0 ? ZOOM_STEPS.find((z) => z > zoom + ZOOM_EPS) ?? ZOOM_STEPS[ZOOM_STEPS.length - 1]!
      : [...ZOOM_STEPS].reverse().find((z) => z < zoom - ZOOM_EPS) ?? ZOOM_STEPS[0];
    setZoom(next);
    void rf.zoomTo(next);
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    // `c` copies the current selection's reference, never while typing in a field
    const t = e.target as HTMLElement;
    if (e.key !== COPY_KEY || e.ctrlKey || e.metaKey || e.altKey || !sel.selection) return;
    if (t.closest("input, textarea, select, [contenteditable='true']")) return;
    void copyText(buildReference(data, sel.selection));
  };

  return (
    <div className={styles.wrap} tabIndex={0} onKeyDown={onKey} aria-label="Flow diagram">
      <div className={styles.controls}>
        <h2 className={styles.heading}>Flow</h2>
        <WorkflowLine data={data} />
        {sel.selection ? (
          <span className={styles.group} data-testid="flow-diagram-ref" data-ref={selParam(sel.selection)}>
            <RefChip data={data} selection={sel.selection} />
            <CopyReference data={data} selection={sel.selection} icon />
          </span>
        ) : null}
        <span className={`${styles.group} ${styles.segmented}`} role="group" aria-label="Lens">
          {[Lens.Time, Lens.Cost].map((l) => (
            <button key={l} type="button" aria-pressed={sel.lens === l} onClick={() => sel.setLens(l)}>
              {l === Lens.Time ? "Time" : "Cost"}
            </button>
          ))}
        </span>
        <span className={styles.group} role="group" aria-label="Zoom">
          <button type="button" aria-label="Zoom out" onClick={() => step(-1)}>−</button>
          <span data-testid="flow-zoom" aria-live="polite">{Math.round(zoom * 100)}%</span>
          <button type="button" aria-label="Zoom in" onClick={() => step(1)}>+</button>
          <button type="button" onClick={fit}>Fit</button>
        </span>
      </div>
      <div ref={canvasRef} className={styles.canvas} style={geo.bus ? undefined : { height: geo.canvas.h * zoom + CANVAS_ROOM }}>
        <p className={styles.legend} aria-hidden="true">
          {sel.lens === Lens.Cost ? LEGEND_COST : LEGEND_TIME}<br />{LEGEND_ARROWS}
        </p>
        <ReactFlow
          nodes={nodes}
          edges={[]}
          nodeTypes={NODE_TYPES}
          defaultViewport={{ x: 0, y: 0, zoom: DEFAULT_ZOOM }}
          minZoom={ZOOM_STEPS[0]}
          maxZoom={ZOOM_STEPS[ZOOM_STEPS.length - 1]}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          // HM-6: a plain wheel scrolls the page; React Flow then zooms only on a ctrl wheel (and trackpad pinch)
          preventScrolling={false}
          // HM-30: React Flow's corner credit link rendered as an empty grey box under the page styles
          proOptions={PRO_OPTIONS}
          // React Flow sets pointer-events:none on nodes that are neither selectable nor draggable unless a node
          // handler exists; the box's own button does the selecting
          onNodeClick={noop}
          onMove={(_e, vp) => setZoom(vp.zoom)}
          onInit={() => {
            ready.current = true;
            fit();
          }}
          onPaneClick={() => sel.clear()}
        >
          <ViewportPortal>
            <Edges data={data} motion={motion} onOpenInstructions={onOpenInstructions} />
          </ViewportPortal>
        </ReactFlow>
      </div>
      {/* HM-50: under the diagram, so the header line has room for the workflow's name and CI mode */}
      <p className={styles.hint}>{FLOW_HINT}</p>
      <Children data={data} />
    </div>
  );
}
