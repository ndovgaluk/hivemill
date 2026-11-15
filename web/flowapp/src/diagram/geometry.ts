// HM-50: where the diagram's boxes, frames and arrows sit. The old workflow uses the app's fixed layout (layout.ts);
// an engine run sends its own (web/flowdefs.py geometry), so a step added to one workflow needs no change here.
import type { FlowData, Pt } from "../types";
import { CANVAS_H, CANVAS_W, EDGES, FRAMES, POSITIONS, type EdgeGeo, type Frame } from "./layout";

export interface Geometry {
  canvas: { w: number; h: number };
  boxes: Partial<Record<string, { x: number; y: number }>>;
  frames: Partial<Record<string, Frame>>;
  edges: Partial<Record<string, EdgeGeo>>;
  /** The old workflow's lead-to-workers bus is drawn from its own branches (layout.ts BUS_BRANCHES). */
  bus: boolean;
}

const FIXED: Geometry = { canvas: { w: CANVAS_W, h: CANVAS_H }, boxes: POSITIONS, frames: FRAMES, edges: EDGES, bus: true };

export function geometryOf(data: FlowData): Geometry {
  const l = data.layout;
  if (!l) return FIXED;
  const edges: Partial<Record<string, EdgeGeo>> = {};
  for (const [id, e] of Object.entries(l.edges)) edges[id] = { points: e.points as Pt[], label: e.label as Pt };
  return { canvas: l.canvas, boxes: l.boxes, frames: l.frames, edges, bus: false };
}
