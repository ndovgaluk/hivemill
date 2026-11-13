// The one selection the diagram, timeline and inspector share (design: DVDG-551 attachment, selection rules).
import { createContext, createElement, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";

import { Lens, SelectionKind, TimelineTab, UrlParam, type Dir, type EdgeId, type LaneId, type NodeId } from "./constants";
import { groupOf, members } from "./groups";
import { parseSel, selParam } from "./reference/reference";
import type { FlowData, FlowEvent } from "./types";

const isOf = <T extends Record<string, string>>(o: T, v: string | null): v is T[keyof T] =>
  v !== null && (Object.values(o) as string[]).includes(v);

export interface Selection {
  kind: SelectionKind;
  id: string;
}

export interface Hot {
  nodes: Set<NodeId>;
  edges: Set<EdgeId>;
  lanes: Set<LaneId>;
  events: Set<string>;
  /** Direction along the hot edge (event selected), else null. */
  dir: Dir | null;
  /** Seconds from start of the selected event, else null. */
  cursor: number | null;
  /** The box that sent the selected event (it pulses), else null. */
  sender: NodeId | null;
}

export interface SelectionState {
  selection: Selection | null;
  lens: Lens;
  tab: TimelineTab;
}

export const Act = { Select: "select", Clear: "clear", Step: "step", SetLens: "setLens", SetTab: "setTab" } as const;

export type Action =
  | { type: typeof Act.Select; selection: Selection }
  | { type: typeof Act.Clear }
  | { type: typeof Act.Step; delta: 1 | -1; events: FlowEvent[] }
  | { type: typeof Act.SetLens; lens: Lens }
  | { type: typeof Act.SetTab; tab: TimelineTab };

export const initialState: SelectionState = { selection: null, lens: Lens.Time, tab: TimelineTab.Lanes };

/** Shown when the address names an item this flow no longer has (DVDG-564). */
export const NOT_IN_FLOW = "That item is not in this flow any more";

const same = (a: Selection | null, b: Selection) => a !== null && a.kind === b.kind && a.id === b.id;

/** Events in time order (stable on ties); events without a time go last. */
export function timeOrder(events: FlowEvent[]): FlowEvent[] {
  return events
    .map((e, i) => ({ e, i }))
    .sort((a, b) => (a.e.t_s ?? Infinity) - (b.e.t_s ?? Infinity) || a.i - b.i)
    .map(({ e }) => e);
}

export function reducer(state: SelectionState, action: Action): SelectionState {
  switch (action.type) {
    case Act.Select:
      // selecting the same thing again clears it
      return { ...state, selection: same(state.selection, action.selection) ? null : action.selection };
    case Act.Clear:
      return { ...state, selection: null };
    case Act.SetLens:
      return { ...state, lens: action.lens };
    case Act.SetTab:
      return { ...state, tab: action.tab };
    case Act.Step: {
      const ordered = timeOrder(action.events);
      if (ordered.length === 0) return state;
      const cur = state.selection?.kind === SelectionKind.Event ? ordered.findIndex((e) => e.id === state.selection?.id) : -1;
      const next = cur === -1 ? (action.delta === 1 ? 0 : ordered.length - 1) : Math.min(ordered.length - 1, Math.max(0, cur + action.delta));
      const ev = ordered[next];
      return ev ? { ...state, selection: { kind: SelectionKind.Event, id: ev.id } } : state;
    }
  }
}

const empty = (): Hot => ({ nodes: new Set(), edges: new Set(), lanes: new Set(), events: new Set(), dir: null, cursor: null,
  sender: null });

/** What the current selection lights up in every view. */
export function derive(data: FlowData | null, selection: Selection | null): Hot {
  const hot = empty();
  if (!data || !selection) return hot;
  const lanesOf = (nodes: Set<NodeId>) => data.lanes.filter((l) => nodes.has(l.node)).forEach((l) => hot.lanes.add(l.id));
  if (selection.kind === SelectionKind.Node) {
    const id = selection.id as NodeId;
    hot.nodes.add(id);
    // HM-17: a box also owns the arrows and steps addressed to its group (e.g. "rework" leaves the Review gate frame)
    const group = groupOf(data, id);
    const mine = (n: string | null | undefined) => n === id || (group !== null && n === group);
    data.edges.filter((e) => mine(e.from) || e.to.some(mine)).forEach((e) => hot.edges.add(e.id));
    data.events.filter((e) => mine(e.from_node) || mine(e.to_node)).forEach((e) => hot.events.add(e.id));
    lanesOf(hot.nodes);
  } else if (selection.kind === SelectionKind.Edge) {
    const edge = data.edges.find((e) => e.id === selection.id);
    if (!edge) return hot;
    hot.edges.add(edge.id);
    [edge.from, ...edge.to].flatMap((n) => members(data, n)).forEach((n) => hot.nodes.add(n as NodeId));
    data.events.filter((e) => e.edge === edge.id).forEach((e) => hot.events.add(e.id));
    lanesOf(hot.nodes);
  } else {
    const ev = data.events.find((e) => e.id === selection.id);
    if (!ev) return hot;
    hot.events.add(ev.id);
    if (ev.edge) hot.edges.add(ev.edge);
    for (const n of [ev.from_node, ev.to_node]) if (n) members(data, n).forEach((m) => hot.nodes.add(m as NodeId));
    if (ev.lane) hot.lanes.add(ev.lane);
    hot.dir = ev.dir;
    hot.cursor = ev.t_s;
    hot.sender = ev.from_node;
  }
  return hot;
}

export interface SelectionApi extends SelectionState {
  hot: Hot;
  select: (selection: Selection) => void;
  clear: () => void;
  stepNext: () => void;
  stepPrev: () => void;
  setLens: (lens: Lens) => void;
  setTab: (tab: TimelineTab) => void;
  /** A message for the owner (an address naming an item that is gone), else null. */
  notice: string | null;
}

const Ctx = createContext<SelectionApi | null>(null);

export function SelectionProvider({ data, children }: { data: FlowData | null; children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [notice, setNotice] = useState<string | null>(null);
  const restored = useRef(false);
  const events = data?.events;

  // DVDG-564: the address mirrors the selection, timeline tab and lens (replaceState: no history entries)
  useEffect(() => {
    if (!restored.current) return;
    const url = new URL(window.location.href);
    if (state.selection) url.searchParams.set(UrlParam.Sel, selParam(state.selection));
    else url.searchParams.delete(UrlParam.Sel);
    url.searchParams.set(UrlParam.Tab, state.tab);
    url.searchParams.set(UrlParam.Lens, state.lens);
    window.history.replaceState(window.history.state, "", url);
  }, [state.selection, state.tab, state.lens]);

  // … and is read back once, when the data is first there
  useEffect(() => {
    if (restored.current || !data) return;
    restored.current = true;
    const q = new URL(window.location.href).searchParams;
    const tab = q.get(UrlParam.Tab);
    const lens = q.get(UrlParam.Lens);
    if (isOf(TimelineTab, tab)) dispatch({ type: Act.SetTab, tab });
    if (isOf(Lens, lens)) dispatch({ type: Act.SetLens, lens });
    const raw = q.get(UrlParam.Sel);
    if (raw) {
      const sel = parseSel(raw, data);
      if (sel) dispatch({ type: Act.Select, selection: sel });
      else setNotice(NOT_IN_FLOW);
    }
  }, [data]);

  const api = useMemo<SelectionApi>(
    () => ({
      ...state,
      notice,
      hot: derive(data, state.selection),
      select: (selection) => {
        setNotice(null);
        dispatch({ type: Act.Select, selection });
      },
      clear: () => dispatch({ type: Act.Clear }),
      stepNext: () => dispatch({ type: Act.Step, delta: 1, events: events ?? [] }),
      stepPrev: () => dispatch({ type: Act.Step, delta: -1, events: events ?? [] }),
      setLens: (lens) => dispatch({ type: Act.SetLens, lens }),
      setTab: (tab) => dispatch({ type: Act.SetTab, tab }),
    }),
    [state, data, events, notice],
  );
  return createElement(Ctx.Provider, { value: api }, children);
}

export function useSelection(): SelectionApi {
  const api = useContext(Ctx);
  if (!api) throw new Error("useSelection outside SelectionProvider");
  return api;
}
