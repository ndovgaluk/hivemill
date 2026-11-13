// "Copy for investigation" (DVDG-564): ids and facts only, never message text, so it is safe to paste anywhere.
import { RefPrefix, Scope, SelectionKind, UrlParam } from "../constants";
import type { Selection } from "../selection";
import type { FlowData } from "../types";

export const RefLabel = {
  Head: "Hivemill flow reference",
  Scope: "scope:",
  Item: "item:",
  When: "when:",
  Who: "who:",
  What: "what:",
  Link: "link:",
} as const;

const SEP = " ";
const ARROW = " → ";

/** The short key shown on chips and used in the address: V12, box:coders, arrow:rw. */
export function selParam(s: Selection): string {
  if (s.kind === SelectionKind.Node) return `${RefPrefix.Box}${s.id}`;
  if (s.kind === SelectionKind.Edge) return `${RefPrefix.Arrow}${s.id}`;
  return s.id;
}

/** The address form back to a selection, or null when that item is not in this payload. */
export function parseSel(raw: string, data: FlowData): Selection | null {
  if (raw.startsWith(RefPrefix.Box)) {
    const id = raw.slice(RefPrefix.Box.length);
    return data.nodes.some((n) => n.id === id) ? { kind: SelectionKind.Node, id } : null;
  }
  if (raw.startsWith(RefPrefix.Arrow)) {
    const id = raw.slice(RefPrefix.Arrow.length);
    return data.edges.some((e) => e.id === id) ? { kind: SelectionKind.Edge, id } : null;
  }
  return data.events.some((e) => e.id === raw) ? { kind: SelectionKind.Event, id: raw } : null;
}

/** One line the agent can act on: the goal or task, then the key ("T-0003 V12", "G-001 box:coders"). */
export function qualifiedKey(data: FlowData, s: Selection): string {
  const owner = s.kind === SelectionKind.Event ? (data.events.find((e) => e.id === s.id)?.task_id ?? data.goal_id ?? data.id) : data.id;
  return `${owner}${SEP}${selParam(s)}`;
}

/** This page's address with the selection in it (other parameters, e.g. the dev page's scope and id, are kept). */
export function buildLink(s: Selection, href: string = window.location.href): string {
  const url = new URL(href);
  url.searchParams.set(UrlParam.Sel, selParam(s));
  return url.toString();
}

export function buildReference(data: FlowData, s: Selection, href?: string): string {
  const scope = data.scope === Scope.Task && data.goal_id
    ? `${RefLabel.Scope} ${data.scope} ${data.id} (goal ${data.goal_id})`
    : `${RefLabel.Scope} ${data.scope} ${data.id}`;
  const lines = [RefLabel.Head, scope];
  const label = (id: string | null | undefined) => data.nodes.find((n) => n.id === id)?.label ?? id ?? "?";
  if (s.kind === SelectionKind.Event) {
    const e = data.events.find((x) => x.id === s.id);
    lines.push(`${RefLabel.Item} ${qualifiedKey(data, s)}${e ? ` (${e.ref.table}.id=${e.ref.rowid})` : ""}`);
    if (e) {
      lines.push(`${RefLabel.When} ${e.ts}`);
      lines.push(`${RefLabel.Who} ${e.from ?? "?"}${ARROW}${e.to ?? "?"} [${label(e.from_node)}${ARROW}${label(e.to_node)}]`);
      lines.push(`${RefLabel.What} ${e.title}`);
    }
  } else if (s.kind === SelectionKind.Node) {
    const n = data.nodes.find((x) => x.id === s.id);
    lines.push(`${RefLabel.Item} ${qualifiedKey(data, s)}${n?.agents.length ? ` (agents: ${n.agents.map((a) => a.name).join(", ")})` : ""}`);
    lines.push(`${RefLabel.What} ${label(s.id)}`);
  } else {
    const ed = data.edges.find((x) => x.id === s.id);
    const ins = data.events.filter((e) => e.edge === s.id && e.is_instruction).map((e) => e.id);
    lines.push(`${RefLabel.Item} ${qualifiedKey(data, s)}${ins.length ? ` (instructions: ${ins.join(", ")})` : ""}`);
    if (ed) lines.push(`${RefLabel.What} ${label(ed.from)}${ARROW}${ed.to.map(label).join(", ")}`);
  }
  lines.push(`${RefLabel.Link} ${buildLink(s, href)}`);
  return lines.join("\n");
}

/** Clipboard write; false when the browser offers no clipboard here (the caller shows a text area instead). */
export async function copyText(text: string): Promise<boolean> {
  if (!navigator.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
