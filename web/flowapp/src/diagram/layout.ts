// Fixed layout of the design mock (grilling DVDG-552 Q9): command row on top, work row below, rework loop under it.
// HM-17: the review gate is a dashed frame holding Reviewer above QA, so the work row is taller in that column.
import { EdgeId, NodeId } from "../constants";

export const NODE_W = 140;
export const NODE_H = 64;
export const CANVAS_W = 1040;
export const CANVAS_H = 376;

const GATE_X = 466;   // HM-17: the frame (10 px outside) sits 98 px from Coders: room for the wait chip and a visible arrow
const WORK_Y = 176;
const JUDGE_X = 684;   // the frame right edge + 68
const STACK_GAP = 12;                         // between Reviewer and QA inside the frame
const FRAME_PAD = 10;                         // the frame is drawn this far outside its boxes

/** Boxes by node id; a node without a place (a group id, or a node from a newer server) is not drawn. */
export const POSITIONS: Partial<Record<NodeId, { x: number; y: number }>> = {
  [NodeId.Boss]: { x: 10, y: 16 },
  [NodeId.Director]: { x: 218, y: 16 },
  [NodeId.Lead]: { x: 426, y: 16 },
  [NodeId.System]: { x: 634, y: 16 },
  [NodeId.Pm]: { x: 10, y: WORK_Y },
  [NodeId.Coders]: { x: 218, y: WORK_Y },
  [NodeId.Reviewer]: { x: GATE_X, y: WORK_Y },
  [NodeId.Qa]: { x: GATE_X, y: WORK_Y + NODE_H + STACK_GAP },
  [NodeId.Judge]: { x: JUDGE_X, y: WORK_Y },
  [NodeId.Main]: { x: JUDGE_X + NODE_W + 68, y: WORK_Y },
  [NodeId.Wait]: { x: 842, y: 16 },   // top right, clear of the arrows: it belongs to no role
};

export interface Frame { x: number; y: number; w: number; h: number }

/** The dashed group frames (HM-17), by group id: 10 px outside the group's boxes. */
export const FRAMES: Partial<Record<NodeId, Frame>> = {
  [NodeId.Gate]: {
    x: GATE_X - FRAME_PAD,
    y: WORK_Y - FRAME_PAD,
    w: NODE_W + 2 * FRAME_PAD,
    h: 2 * NODE_H + STACK_GAP + 2 * FRAME_PAD,
  },
};
const GATE = FRAMES[NodeId.Gate]!;
const GATE_MID = GATE.x + GATE.w / 2;
const GATE_BOTTOM = GATE.y + GATE.h;           // 326

type Pt = [number, number];

/** Polyline from the edge's `from` end to its `to` end, and where the label chip sits. */
export interface EdgeGeo {
  points: Pt[];
  label: Pt;
}

const BUS_Y = 128;
const LEAD_BOTTOM: Pt = [496, 80];
const busTo = (x: number, y = WORK_Y): Pt[] => [LEAD_BOTTOM, [LEAD_BOTTOM[0], BUS_Y], [x, BUS_Y], [x, y]];
const REWORK_Y = GATE_BOTTOM + 20;

export const EDGES: Record<Exclude<EdgeId, typeof EdgeId.Bus>, EdgeGeo> = {
  [EdgeId.BossDirector]: { points: [[150, 48], [218, 48]], label: [184, 30] },
  [EdgeId.DirectorLead]: { points: [[358, 48], [426, 48]], label: [392, 30] },
  [EdgeId.SystemLead]: { points: [[634, 48], [566, 48]], label: [600, 30] },
  [EdgeId.PmCoders]: { points: [[150, 208], [218, 208]], label: [184, 190] },
  // the review arrows end and start on the frame, not on one of its boxes
  [EdgeId.CodersGate]: { points: [[358, 208], [GATE.x, 208]], label: [(358 + GATE.x) / 2, 190] },
  [EdgeId.GateJudge]: { points: [[GATE.x + GATE.w, 208], [JUDGE_X, 208]], label: [(GATE.x + GATE.w + JUDGE_X) / 2, 190] },
  [EdgeId.JudgeMain]: { points: [[JUDGE_X + NODE_W, 208], [JUDGE_X + NODE_W + 68, 208]], label: [JUDGE_X + NODE_W + 34, 190] },
  [EdgeId.Rework]: {
    points: [[GATE_MID, GATE_BOTTOM], [GATE_MID, REWORK_Y], [288, REWORK_Y], [288, WORK_Y + NODE_H]],
    label: [392, REWORK_Y + 10],
  },
};

/** The lead-to-workers bus: one branch per worker box (or group frame), drawn and animated separately. */
export const BUS_BRANCHES: Partial<Record<NodeId, Pt[]>> = {
  [NodeId.Pm]: busTo(80),
  [NodeId.Coders]: busTo(288),
  [NodeId.Gate]: busTo(GATE_MID, GATE.y),
  [NodeId.Judge]: busTo(JUDGE_X + NODE_W / 2),
};
export const BUS_LABEL: Pt = [392, 112];

export const toPath = (pts: Pt[]) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");

export const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
export const DEFAULT_ZOOM = 1;
