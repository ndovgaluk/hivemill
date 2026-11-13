import { describe, expect, it } from "vitest";

import { EdgeId, NodeId, SelectionKind } from "../constants";
import goal from "../fixtures/goal.json";
import { Act, derive, initialState, reducer, timeOrder, type SelectionState } from "../selection";
import type { FlowData } from "../types";

const data = goal as unknown as FlowData;
const ids = <T>(s: Set<T>) => [...s].sort();

describe("selection", () => {
  it("selecting a node marks its lanes and events hot", () => {
    const hot = derive(data, { kind: SelectionKind.Node, id: NodeId.Coders });
    expect(ids(hot.nodes)).toEqual([NodeId.Coders]);
    expect(ids(hot.lanes)).toEqual(data.lanes.filter((l) => l.node === NodeId.Coders).map((l) => l.id).sort());
    const want = data.events.filter((e) => e.from_node === NodeId.Coders || e.to_node === NodeId.Coders).map((e) => e.id);
    expect(want.length).toBeGreaterThan(0);
    expect(ids(hot.events)).toEqual(want.sort());
  });

  it("selecting an edge marks both ends and its events", () => {
    const edge = data.edges.find((e) => e.id === EdgeId.Rework)!;
    const hot = derive(data, { kind: SelectionKind.Edge, id: edge.id });
    expect(ids(hot.nodes)).toEqual([edge.from, ...edge.to].sort());
    expect(ids(hot.edges)).toEqual([edge.id]);
    const want = data.events.filter((e) => e.edge === edge.id).map((e) => e.id);
    expect(want.length).toBeGreaterThan(0);
    expect(ids(hot.events)).toEqual(want.sort());
  });

  it("selecting an event marks its edge, direction and cursor", () => {
    const ev = data.events.find((e) => e.edge !== null && e.t_s !== null)!;
    const hot = derive(data, { kind: SelectionKind.Event, id: ev.id });
    expect(ids(hot.edges)).toEqual([ev.edge]);
    expect(hot.dir).toBe(ev.dir);
    expect(hot.cursor).toBe(ev.t_s);
    expect(ids(hot.events)).toEqual([ev.id]);
  });

  it("selecting the same thing twice clears the selection", () => {
    const sel = { kind: SelectionKind.Node, id: NodeId.Gate };
    const once = reducer(initialState, { type: Act.Select, selection: sel });
    expect(once.selection).toEqual(sel);
    expect(reducer(once, { type: Act.Select, selection: sel }).selection).toBeNull();
  });

  it("step forward and back walk events in t_s order and stop at the ends", () => {
    const ordered = timeOrder(data.events);
    const step = (s: SelectionState, delta: 1 | -1) => reducer(s, { type: Act.Step, delta, events: data.events });
    let s = step(initialState, 1);
    expect(s.selection?.id).toBe(ordered[0]!.id);
    s = step(s, 1);
    expect(s.selection?.id).toBe(ordered[1]!.id);
    s = step(step(s, -1), -1);
    expect(s.selection?.id).toBe(ordered[0]!.id);   // stays at the first event
    for (let i = 0; i < ordered.length + 2; i++) s = step(s, 1);
    expect(s.selection?.id).toBe(ordered[ordered.length - 1]!.id);
    const times = ordered.map((e) => e.t_s ?? Infinity);
    expect([...times].sort((a, b) => a - b)).toEqual(times);
  });
});
