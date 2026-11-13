import type { FlowData, FlowEvent } from "../types";

/** The axis length in seconds: elapsed time, stretched to cover any later event or span end. */
export function axisLength(data: FlowData): number {
  let max = data.elapsed_s ?? 0;
  for (const e of data.events) if (e.t_s !== null) max = Math.max(max, e.t_s);
  for (const l of data.lanes) for (const r of l.rows) for (const s of r.spans) if (s.end_s !== null) max = Math.max(max, s.end_s);
  return Math.max(1, max);
}

export const pct = (s: number, total: number) => Math.round(Math.min(100, Math.max(0, (s / total) * 100)) * 100) / 100;

/** HH:MM of the DB timestamp as recorded (its own offset), so the view matches the factory's clock. */
export const clock = (ts: string | null | undefined) => (ts && ts.length >= 16 ? ts.slice(11, 16) : "");

export const route = (e: FlowEvent) => `${e.from ?? e.from_node ?? "?"} to ${e.to ?? e.to_node ?? "?"}`;

export const markName = (e: FlowEvent) => `${clock(e.ts)} ${route(e)}: ${e.title}`;

export const ZOOMS = [1, 2, 4, 8] as const;
export const QUIET_GAP_S = 10 * 60;   // a phase that starts after this much silence gets a note (design: 10 min)

const MIN = 60, HOUR = 3600, DAY = 86400;
const STEPS = [MIN, 5 * MIN, 15 * MIN, 30 * MIN, HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 7 * DAY];
const TICKS_PER_SCREEN = 6;

/** Axis ticks: a round step giving about six ticks per screen width at this zoom. */
export function ticks(total: number, zoom: number): { t: number; withDate: boolean }[] {
  const step = STEPS.find((s) => s >= total / (TICKS_PER_SCREEN * zoom)) ?? STEPS[STEPS.length - 1]!;
  const out = [];
  for (let t = 0; t <= total; t += step) out.push({ t, withDate: step >= 12 * HOUR || total > DAY });
  return out;
}

/** Wall-clock label of start + t seconds, in the start timestamp's own UTC offset (as clock() does). */
export function tickLabel(start: string, t: number, withDate: boolean): string {
  const m = /([+-])(\d\d):(\d\d)$/.exec(start);
  const off = m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0;
  const ms = Date.parse(start);
  if (Number.isNaN(ms)) return "";
  const iso = new Date(ms + t * 1000 + off * 60000).toISOString();
  return withDate ? `${iso.slice(5, 10)} ${iso.slice(11, 16)}` : iso.slice(11, 16);
}
