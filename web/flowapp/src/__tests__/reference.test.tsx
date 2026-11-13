import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Diagram } from "../diagram/Diagram";
import { Lens, RefPrefix, SelectionKind, SourceTable, TimelineTab, UrlParam } from "../constants";
import goalFixture from "../fixtures/goal.json";
import taskFixture from "../fixtures/task.json";
import { Inspector } from "../inspector/Inspector";
import { DialogsProvider, useDialogs, type DialogsApi } from "../instructions/Dialogs";
import { COPIED_LABEL, COPY_LABEL } from "../reference/CopyReference";
import { buildReference, RefLabel } from "../reference/reference";
import { NOT_IN_FLOW, SelectionProvider, timeOrder, useSelection, type SelectionApi } from "../selection";
import { Timeline } from "../timeline/Timeline";
import type { FlowData } from "../types";

const task = () => structuredClone(taskFixture) as unknown as FlowData;
const goal = () => structuredClone(goalFixture) as unknown as FlowData;
const HREF = `${window.location.origin}/`;

let sel: SelectionApi | null = null;
let dialogs: DialogsApi | null = null;
function Probe() {
  sel = useSelection();
  dialogs = useDialogs();
  return null;
}

function show(data: FlowData) {
  render(
    <SelectionProvider data={data}>
      <DialogsProvider data={data}>
        <Probe />
        <Diagram data={data} />
        <Inspector data={data} />
        <Timeline data={data} />
      </DialogsProvider>
    </SelectionProvider>,
  );
}

let writeText: ReturnType<typeof vi.fn>;
beforeEach(() => {
  window.history.replaceState(null, "", HREF);
  writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});
afterEach(() => {
  sel = dialogs = null;
  vi.restoreAllMocks();
});

const verdictOf = (d: FlowData) => d.events.find((e) => e.ref.table === SourceTable.Verdicts)!;

describe("buildReference", () => {
  it("reference text for an event", () => {
    const d = task();
    const ev = verdictOf(d);
    const lines = buildReference(d, { kind: SelectionKind.Event, id: ev.id }, HREF).split("\n");
    const label = (id: string | null) => d.nodes.find((n) => n.id === id)!.label;
    expect(lines).toEqual([
      RefLabel.Head,
      `${RefLabel.Scope} task ${d.id} (goal ${d.goal_id})`,
      `${RefLabel.Item} ${ev.task_id} ${ev.id} (verdicts.id=${ev.ref.rowid})`,
      `${RefLabel.When} ${ev.ts}`,
      `${RefLabel.Who} ${ev.from} → ${ev.to} [${label(ev.from_node)} → ${label(ev.to_node)}]`,
      `${RefLabel.What} ${ev.title}`,
      `${RefLabel.Link} ${HREF}?${UrlParam.Sel}=${ev.id}`,
    ]);
    expect(ev.id).toBe(`V${ev.ref.rowid}`);
  });

  it("reference text for a box and for an arrow", () => {
    const d = goal();
    const node = d.nodes.find((n) => n.agents.length)!;
    const box = buildReference(d, { kind: SelectionKind.Node, id: node.id }, HREF);
    expect(box).toContain(`${RefLabel.Item} ${d.id} ${RefPrefix.Box}${node.id} (agents: ${node.agents.map((a) => a.name).join(", ")})`);
    const edge = d.edges.find((e) => d.events.some((x) => x.edge === e.id && x.is_instruction))!;
    const ins = d.events.filter((x) => x.edge === edge.id && x.is_instruction).map((x) => x.id);
    const arrow = buildReference(d, { kind: SelectionKind.Edge, id: edge.id }, HREF);
    expect(arrow).toContain(`${RefLabel.Item} ${d.id} ${RefPrefix.Arrow}${edge.id} (instructions: ${ins.join(", ")})`);
  });

  it("reference never contains message text", () => {
    const d = goal();
    d.show_text = true;
    const ev = d.events.find((e) => e.body_html)!;
    ev.body_html = "<p>SECRET-INSTRUCTION</p>";
    for (const kind of [SelectionKind.Event, SelectionKind.Node, SelectionKind.Edge]) {
      const id = kind === SelectionKind.Event ? ev.id : kind === SelectionKind.Node ? ev.from_node! : ev.edge ?? d.edges[0]!.id;
      expect(buildReference(d, { kind, id }, HREF)).not.toContain("SECRET-INSTRUCTION");
    }
  });
});

describe("copy controls", () => {
  it("Copy for investigation copies the reference and confirms", async () => {
    const d = task();
    const ev = verdictOf(d);
    show(d);
    act(() => sel!.select({ kind: SelectionKind.Event, id: ev.id }));
    const btn = screen.getAllByTestId("flow-copy-ref").find((b) => b.textContent === COPY_LABEL)!;
    fireEvent.click(btn);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(buildReference(d, { kind: SelectionKind.Event, id: ev.id })));
    await waitFor(() => expect(btn.textContent).toBe(COPIED_LABEL));
  });

  it("falls back to a selected text area when the clipboard is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    const d = task();
    show(d);
    act(() => sel!.select({ kind: SelectionKind.Event, id: verdictOf(d).id }));
    fireEvent.click(screen.getAllByTestId("flow-copy-ref").find((b) => b.textContent === COPY_LABEL)!);
    const area = (await screen.findByRole("textbox", { name: "Reference to copy" })) as HTMLTextAreaElement;
    expect(area.readOnly).toBe(true);
    expect(area.value).toContain(RefLabel.Head);
    expect(document.activeElement).toBe(area);
  });

  it("id chip copies the qualified key", async () => {
    const d = task();
    const ev = verdictOf(d);
    show(d);
    act(() => sel!.select({ kind: SelectionKind.Event, id: ev.id }));
    expect(screen.getAllByText(ev.id).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Copy reference" })[0]!);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(`${ev.task_id} ${ev.id}`));
  });

  it("the button exists in every detail view", () => {
    const d = goal();
    const ev = d.events.find((e) => e.is_instruction && e.edge)!;
    show(d);
    for (const s of [{ kind: SelectionKind.Event, id: ev.id }, { kind: SelectionKind.Node, id: ev.from_node! }, { kind: SelectionKind.Edge, id: ev.edge! }]) {
      act(() => sel!.select(s));
      expect(screen.getAllByTestId("flow-copy-ref").length).toBeGreaterThan(0);
    }
    act(() => dialogs!.openInstructions(ev.edge!));
    expect(screen.getByRole("dialog").querySelector('[data-testid="flow-copy-ref"]')).not.toBeNull();
    act(() => screen.getByRole("button", { name: "Close" }).click());
    act(() => dialogs!.openEvents(ev.from_node!));
    expect(screen.getByRole("dialog").querySelectorAll('[data-testid="flow-copy-ref"]').length).toBeGreaterThan(0);
    act(() => screen.getByRole("button", { name: "Close" }).click());
    fireEvent.click(screen.getByRole("button", { name: "Sequence" }));
    act(() => sel!.select({ kind: SelectionKind.Event, id: ev.id }));   // opens its phase
    expect(document.querySelectorAll('[data-testid^="flow-phase-"] [data-testid="flow-copy-ref"]').length).toBeGreaterThan(0);
  });

  it("the diagram chip follows Next event and c copies, but not in an input", async () => {
    const d = goal();
    const ordered = timeOrder(d.events);
    show(d);
    act(() => sel!.stepNext());
    expect(screen.getByTestId("flow-diagram-ref").getAttribute("data-ref")).toBe(ordered[0]!.id);
    act(() => sel!.stepNext());
    expect(screen.getByTestId("flow-diagram-ref").getAttribute("data-ref")).toBe(ordered[1]!.id);
    const diagram = screen.getByLabelText("Flow diagram");
    fireEvent.keyDown(diagram, { key: "c" });
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const input = document.createElement("input");
    diagram.appendChild(input);
    fireEvent.keyDown(input, { key: "c" });
    expect(writeText).toHaveBeenCalledTimes(1);
  });
});

describe("address", () => {
  it("selection, tab and lens are written to the address", () => {
    const d = task();
    const ev = verdictOf(d);
    show(d);
    act(() => sel!.select({ kind: SelectionKind.Event, id: ev.id }));
    let q = new URL(window.location.href).searchParams;
    expect(q.get(UrlParam.Sel)).toBe(ev.id);
    act(() => sel!.setLens(Lens.Cost));
    act(() => sel!.setTab(TimelineTab.Sequence));
    act(() => sel!.clear());
    q = new URL(window.location.href).searchParams;
    expect(q.has(UrlParam.Sel)).toBe(false);
    expect(q.get(UrlParam.Lens)).toBe(Lens.Cost);
    expect(q.get(UrlParam.Tab)).toBe(TimelineTab.Sequence);
  });

  it("selection is restored from the address; an unknown id shows the notice", () => {
    const d = task();
    const ev = verdictOf(d);
    window.history.replaceState(null, "", `${HREF}?${UrlParam.Sel}=${ev.id}&${UrlParam.Lens}=${Lens.Cost}`);
    show(d);
    expect(sel!.selection).toEqual({ kind: SelectionKind.Event, id: ev.id });
    expect(sel!.lens).toBe(Lens.Cost);
  });

  it("an id that is not in the payload shows the notice and selects nothing", () => {
    window.history.replaceState(null, "", `${HREF}?${UrlParam.Sel}=V999999`);
    show(task());
    expect(sel!.selection).toBeNull();
    expect(screen.getByText(NOT_IN_FLOW)).toBeTruthy();
  });
});
