import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EventKind, LaneId, NodeId, SelectionKind, Severity, SpanKind } from "../constants";
import goalFixture from "../fixtures/goal.json";
import { fmtDuration } from "../format";
import { SelectionProvider, timeOrder, useSelection, type SelectionApi } from "../selection";
import { COLLAPSE, EXPAND, SEQUENCE_HELP } from "../timeline/Sequence";
import { colourInfo, KIND_INFO } from "../timeline/QuickInfo";
import { markName } from "../timeline/time";
import { Timeline } from "../timeline/Timeline";
import type { FlowData } from "../types";

const fresh = () => structuredClone(goalFixture) as unknown as FlowData;
let api: SelectionApi | null = null;
function Probe() {
  api = useSelection();
  return null;
}

function show(data: FlowData, onOpenInstructions = vi.fn()) {
  render(
    <SelectionProvider data={data}>
      <Probe />
      <Timeline data={data} onOpenInstructions={onOpenInstructions} />
    </SelectionProvider>,
  );
  return onOpenInstructions;
}

afterEach(() => {
  api = null;
});

const withRows = (d: FlowData) => d.lanes.find((l) => l.rows.length > 0)!;

describe("timeline: quick info on a mark (HM-19)", () => {
  const firstOf = (d: FlowData, kind: EventKind) => d.events.find((e) => e.kind === kind && e.t_s !== null && e.lane)!;

  it("a click on a mark selects it and explains each kind of mark", () => {
    const d = fresh();
    show(d);
    for (const kind of [EventKind.Msg, EventKind.Status, EventKind.Verdict]) {
      const e = firstOf(d, kind);
      fireEvent.click(document.querySelector(`[data-mark="${e.id}"]`)!);
      expect(api!.selection).toEqual({ kind: SelectionKind.Event, id: e.id });
      const box = screen.getByTestId("flow-quick-info");
      expect(within(box).getAllByText(KIND_INFO[kind].name).length).toBeGreaterThan(0);   // header and explanation
      expect(box.textContent).toContain(`${KIND_INFO[kind].name}: ${KIND_INFO[kind].means}`);   // the type, not the shape (HM-28)
      expect(box.textContent).not.toMatch(/circle|square/i);
      expect(box.textContent).toContain(colourInfo(e));
      expect(box.textContent).toContain(e.title);
    }
  });

  it("Esc and Close close it; selecting something else hides it", () => {
    const d = fresh();
    show(d);
    const e = firstOf(d, EventKind.Msg);
    const mark = () => document.querySelector(`[data-mark="${e.id}"]`)!;
    fireEvent.click(mark());
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByTestId("flow-quick-info")).toBeNull();
    fireEvent.click(mark());
    fireEvent.click(within(screen.getByTestId("flow-quick-info")).getByRole("button", { name: "Close" }));
    expect(screen.queryByTestId("flow-quick-info")).toBeNull();
    fireEvent.click(mark());
    act(() => api!.select({ kind: SelectionKind.Node, id: NodeId.Lead }));
    expect(screen.queryByTestId("flow-quick-info")).toBeNull();
  });
});

describe("timeline: lanes", () => {
  it("renders one lane per payload lane with its total", () => {
    const d = fresh();
    show(d);
    for (const l of d.lanes) {
      expect(screen.getByTestId(`flow-lane-${l.id}`)).toBeTruthy();
      expect(screen.getByRole("button", { name: l.label })).toBeTruthy();
    }
  });

  it("the Waiting lane totals its wait spans instead of saying unknown (HM-18)", () => {
    const d = fresh();
    const lane = d.lanes.find((l) => l.id === LaneId.Wait)!;
    lane.rows = [{ name: "no agent running", task_id: null, spans: [
      { start_s: 60, end_s: 180, kind: SpanKind.Wait, note: null }, { start_s: 600, end_s: 660, kind: SpanKind.Wait, note: null }] }];
    show(d);
    const label = within(screen.getByTestId(`flow-lane-${LaneId.Wait}`)).getByRole("button", { name: lane.label });
    expect(label.textContent).toContain(fmtDuration(180));
  });

  it("spans are placed by time", () => {
    const d = fresh();
    const lane = withRows(d);
    d.elapsed_s = 1000;
    d.events.forEach((e) => (e.t_s = Math.min(e.t_s ?? 0, 1000)));
    d.lanes.forEach((l) => l.rows.forEach((r) => (r.spans = [])));
    lane.rows[0]!.spans = [{ start_s: 0, end_s: 500, kind: SpanKind.Wait, note: null }];
    show(d);
    const span = screen.getByTestId(`flow-lane-${lane.id}`).querySelector(`[data-kind="${SpanKind.Wait}"]`)!;
    expect(span.getAttribute("data-left")).toBe("0");
    expect(span.getAttribute("data-width")).toBe("50");
  });

  it("clicking a lane label expands its agent rows", () => {
    const d = fresh();
    const lane = withRows(d);
    show(d);
    const btn = screen.getByRole("button", { name: lane.label });
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    for (const r of lane.rows) expect(screen.getByRole("group", { name: r.name })).toBeTruthy();
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("group", { name: lane.rows[0]!.name })).toBeNull();
  });

  it("clicking an event mark selects the event and shows the cursor", () => {
    const d = fresh();
    const ev = d.events.find((e) => e.t_s !== null && e.lane)!;
    show(d);
    const mark = screen.getAllByRole("button", { name: markName(ev) })[0]!;
    fireEvent.click(mark);
    expect(screen.getAllByRole("button", { name: markName(ev) }).some((m) => m.getAttribute("aria-pressed") === "true")).toBe(true);
    expect(screen.getByTestId("flow-cursor")).toBeTruthy();
    expect(api!.selection).toEqual({ kind: SelectionKind.Event, id: ev.id });
  });

  it("selection from outside highlights lanes and expands the event's lane", () => {
    const d = fresh();
    show(d);
    act(() => api!.select({ kind: SelectionKind.Node, id: NodeId.Coders }));
    expect(screen.getByTestId(`flow-lane-${LaneId.Coders}`).getAttribute("data-hot")).toBe("true");
    expect(screen.getByTestId(`flow-lane-${LaneId.Boss}`).getAttribute("data-dim")).toBe("true");
    const ev = d.events.find((e) => e.lane && d.lanes.find((l) => l.id === e.lane)!.rows.length > 0)!;
    act(() => api!.select({ kind: SelectionKind.Event, id: ev.id }));
    const lane = d.lanes.find((l) => l.id === ev.lane)!;
    expect(screen.getByRole("button", { name: lane.label }).getAttribute("aria-expanded")).toBe("true");
  });

  it("zoom widens the track and keeps labels in place", () => {
    show(fresh());
    fireEvent.click(screen.getByRole("button", { name: "Timeline zoom in" }));
    expect(screen.getByTestId("flow-timeline-zoom").textContent).toBe("2x");
    expect(document.querySelector('[data-zoom="2"]')).not.toBeNull();
    expect(document.querySelectorAll('[data-sticky="true"]').length).toBeGreaterThan(0);
  });

  it("Expand all / Collapse all toggles every lane that has rows", () => {
    const d = fresh();
    show(d);
    fireEvent.click(screen.getByRole("button", { name: "Expand all" }));
    for (const l of d.lanes.filter((x) => x.rows.length))
      expect(screen.getByRole("button", { name: l.label }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    for (const l of d.lanes.filter((x) => x.rows.length))
      expect(screen.getByRole("button", { name: l.label }).getAttribute("aria-expanded")).toBe("false");
  });
});

describe("timeline: sequence", () => {
  const toSequence = () => fireEvent.click(screen.getByRole("button", { name: "Sequence" }));

  it("lists phases in order with a summary and flags", () => {
    const d = fresh();
    const failing = d.phases.find((p) =>
      p.event_ids.some((id) => d.events.find((e) => e.id === id)!.kind === EventKind.Verdict
        && d.events.find((e) => e.id === id)!.severity === Severity.Bad))!;
    const nFail = failing.event_ids.filter((id) => {
      const e = d.events.find((x) => x.id === id)!;
      return e.kind === EventKind.Verdict && e.severity === Severity.Bad;
    }).length;
    show(d);
    toSequence();
    const heads = d.phases.map((p) => screen.getByTestId(`flow-phase-${p.id}`));
    expect(heads).toHaveLength(d.phases.length);
    expect(within(screen.getByTestId(`flow-phase-${failing.id}`)).getByText(`${nFail} failed`)).toBeTruthy();
    for (const p of d.phases) expect(within(screen.getByTestId(`flow-phase-${p.id}`)).getByText(p.summary)).toBeTruthy();
  });

  it("opening a phase lists its events in time order with route", () => {
    const d = fresh();
    const p = d.phases.find((x) => x.event_ids.length > 1)!;
    show(d);
    toSequence();
    fireEvent.click(within(screen.getByTestId(`flow-phase-${p.id}`)).getByRole("button", { name: new RegExp(p.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }));
    const items = within(screen.getByTestId(`flow-phase-${p.id}`)).getAllByRole("listitem");
    expect(items.length).toBeGreaterThanOrEqual(p.event_ids.length);
    const first = d.events.find((e) => e.id === p.event_ids[0])!;
    expect(screen.getByTestId(`flow-phase-${p.id}`).textContent).toContain(`${first.from ?? first.from_node} → ${first.to ?? first.to_node}`);
    expect(screen.getByText(SEQUENCE_HELP)).toBeTruthy();
  });

  it("an instruction item opens its text inline and the instruction viewer", () => {
    const d = fresh();
    const ev = d.events.find((e) => e.is_instruction && e.edge && e.kind === EventKind.Msg)!;
    const p = d.phases.find((x) => x.event_ids.includes(ev.id))!;
    const onOpen = show(d);
    toSequence();
    act(() => api!.select({ kind: SelectionKind.Event, id: ev.id }));   // also opens its phase
    const phase = screen.getByTestId(`flow-phase-${p.id}`);
    const row = within(phase).getAllByRole("listitem").find((li) => li.textContent!.includes(ev.title))!;
    fireEvent.click(within(row).getByRole("button", { name: "Instructions ▾" }));
    expect(within(row).getByText("Message")).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: "Open in instruction viewer" }));
    expect(onOpen).toHaveBeenCalledWith(ev.edge, ev.id);
    fireEvent.click(within(row).getByRole("button", { name: "Hide ▴" }));
    expect(within(row).queryByText("Message")).toBeNull();
    // the small button after the title does the same
    fireEvent.click(within(row).getByRole("button", { name: EXPAND }));
    expect(within(row).getByText("Message")).toBeTruthy();
    expect(within(row).getByRole("button", { name: "Hide ▴" })).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: COLLAPSE }));
    expect(within(row).queryByText("Message")).toBeNull();
  });

  it("phases show the time range, action count and quiet gaps", () => {
    const d = fresh();
    show(d);
    toSequence();
    expect(screen.getAllByText(/ actions?$/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/with no new action starting/).length).toBeGreaterThan(0);
  });

  it("a phase row starts with its time range, before the title", () => {
    const d = fresh();
    show(d);
    toSequence();
    const timed = d.phases.filter((p) => p.event_ids.some((id) => d.events.find((e) => e.id === id)?.t_s != null));
    expect(timed.length).toBeGreaterThan(0);
    for (const p of timed) {
      const when = screen.getByTestId(`flow-phase-when-${p.id}`);
      expect(when.textContent).toMatch(/^\d{2}:\d{2}/);
      const title = within(screen.getByTestId(`flow-phase-${p.id}`)).getByText(p.title);
      expect(when.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(screen.queryByText(/ · \d+ actions?$/)).toBeNull();   // the range is no longer at the end of the row
  });

  it("selecting an event elsewhere opens the phase that contains it", () => {
    const d = fresh();
    const p = d.phases[d.phases.length - 1]!;
    show(d);
    toSequence();
    const head = within(screen.getByTestId(`flow-phase-${p.id}`)).getAllByRole("button")[0]!;
    expect(head.getAttribute("aria-expanded")).toBe("false");
    act(() => api!.select({ kind: SelectionKind.Event, id: p.event_ids[0]! }));
    expect(head.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("timeline: both tabs", () => {
  it("Prev event and Next event step the store and the position label follows", () => {
    const d = fresh();
    const ordered = timeOrder(d.events);
    show(d);
    expect(screen.getByTestId("flow-position").textContent).toBe(`– / ${ordered.length}`);
    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    expect(screen.getByTestId("flow-position").textContent).toBe(`3 / ${ordered.length}`);
    expect(api!.selection?.id).toBe(ordered[2]!.id);
    fireEvent.click(screen.getByRole("button", { name: "Prev event" }));
    expect(screen.getByTestId("flow-position").textContent).toBe(`2 / ${ordered.length}`);
  });
});
