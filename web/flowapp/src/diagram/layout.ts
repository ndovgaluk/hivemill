// Fixed layout of the design mock (grilling DVDG-552 Q9): command row on top, work row below, rework loop under it.
import { EdgeId, NodeId } from "../constants";

export const NODE_W = 140;
export const NODE_H = 64;
export const CANVAS_W = 990;
export const CANVAS_H = 300;

export const POSITIONS: Record<NodeId, { x: number; y: number }> = {
  [NodeId.Boss]: { x: 10, y: 16 },
  [NodeId.Director]: { x: 218, y: 16 },
  [NodeId.Lead]: { x: 426, y: 16 },
  [NodeId.System]: { x: 634, y: 16 },
  [NodeId.Pm]: { x: 10, y: 176 },
  [NodeId.Coders]: { x: 218, y: 176 },
  [NodeId.Gate]: { x: 426, y: 176 },
  [NodeId.Judge]: { x: 634, y: 176 },
  [NodeId.Main]: { x: 842, y: 176 },
  [NodeId.Wait]: { x: 842, y: 16 },   // top right, clear of the arrows: it belongs to no role
};

type Pt = [number, number];

/** Polyline from the edge's `from` end to its `to` end, and where the label chip sits. */
export interface EdgeGeo {
  points: Pt[];
  label: Pt;
}

const BUS_Y = 128;
const LEAD_BOTTOM: Pt = [496, 80];
const WORK_TOP = 176;
const busTo = (x: number): Pt[] => [LEAD_BOTTOM, [LEAD_BOTTOM[0], BUS_Y], [x, BUS_Y], [x, WORK_TOP]];

export const EDGES: Record<Exclude<EdgeId, typeof EdgeId.Bus>, EdgeGeo> = {
  [EdgeId.BossDirector]: { points: [[150, 48], [218, 48]], label: [184, 30] },
  [EdgeId.DirectorLead]: { points: [[358, 48], [426, 48]], label: [392, 30] },
  [EdgeId.SystemLead]: { points: [[634, 48], [566, 48]], label: [600, 30] },
  [EdgeId.PmCoders]: { points: [[150, 208], [218, 208]], label: [184, 190] },
  [EdgeId.CodersGate]: { points: [[358, 208], [426, 208]], label: [392, 190] },
  [EdgeId.GateJudge]: { points: [[566, 208], [634, 208]], label: [600, 190] },
  [EdgeId.JudgeMain]: { points: [[774, 208], [842, 208]], label: [808, 190] },
  [EdgeId.Rework]: { points: [[496, 240], [496, 272], [288, 272], [288, 240]], label: [392, 282] },
};

/** The lead-to-workers bus: one branch per worker box, drawn and animated separately. */
export const BUS_BRANCHES: Partial<Record<NodeId, Pt[]>> = {
  [NodeId.Pm]: busTo(80),
  [NodeId.Coders]: busTo(288),
  [NodeId.Gate]: busTo(496),
  [NodeId.Judge]: busTo(704),
};
export const BUS_LABEL: Pt = [392, 112];

export const toPath = (pts: Pt[]) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");

export const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
export const DEFAULT_ZOOM = 1;
