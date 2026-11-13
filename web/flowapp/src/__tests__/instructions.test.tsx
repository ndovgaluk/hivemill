import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NodeId, SelectionKind } from "../constants";
import goalFixture from "../fixtures/goal.json";
import { HIDDEN_TEXT } from "../instructions/Body";
import { DialogsProvider, useDialogs, type DialogsApi } from "../instructions/Dialogs";
import { SelectionProvider, timeOrder, useSelection, type SelectionApi } from "../selection";
import type { FlowData } from "../types";

const fresh = () => structuredClone(goalFixture) as unknown as FlowData;
let sel: SelectionApi | null = null;
let dialogs: DialogsApi | null = null;
function Probe() {
  sel = useSelection();
  dialogs = useDialogs();
  return <button type="button" onClick={() => dialogs!.openInstructions(edgeOf(current!))}>opener</button>;
}
let current: FlowData | null = null;
const edgeOf = (d: FlowData) => d.edges.find((e) => d.events.some((x) => x.edge === e.id && x.is_instruction))!.id;

function show(data: FlowData) {
  current = data;
  render(
    <SelectionProvider data={data}>
      <DialogsProvider data={data}>
        <Probe />
      </DialogsProvider>
    </SelectionProvider>,
  );
}

const label = (d: FlowData, id: string | null | undefined) => d.nodes.find((n) => n.id === id)!.label;
const instructions = (d: FlowData, edgeId: string) => timeOrder(d.events.filter((e) => e.edge === edgeId && e.is_instruction));

afterEach(() => {
  sel = dialogs = current = null;
});

describe("instruction viewer", () => {
  it("opens for an edge with the first instruction selected", () => {
    const d = fresh();
    const edgeId = edgeOf(d);
    const edge = d.edges.find((e) => e.id === edgeId)!;
    show(d);
    act(() => dialogs!.openInstructions(edgeId));
    const dlg = screen.getByRole("dialog", { name: `Instructions: ${label(d, edge.from)} → ${edge.to.map((t) => label(d, t)).join(", ")}: ${edge.label}` });
    const items = within(within(dlg).getByRole("list", { name: "Instructions on this link" })).getAllByRole("button");
    expect(items).toHaveLength(instructions(d, edgeId).length);
    expect(items[0]!.getAttribute("aria-pressed")).toBe("true");
  });

  it("shows who gave the instruction to whom", () => {
    const d = fresh();
    const edgeId = edgeOf(d);
    const first = instructions(d, edgeId)[0]!;
    show(d);
    act(() => dialogs!.openInstructions(edgeId));
    const from = screen.getByRole("region", { name: "From" });
    const to = screen.getByRole("region", { name: "To" });
    expect(from.textContent).toContain(first.from!);
    expect(from.textContent).toContain(label(d, first.from_node));
    expect(to.textContent).toContain(first.to!);
    expect(screen.getByRole("heading", { name: first.title, level: 3 })).toBeTruthy();
  });

  it("renders the server's Markdown and keeps raw HTML inert", () => {
    const d = fresh();
    const edgeId = edgeOf(d);
    const first = instructions(d, edgeId)[0]!;
    // what web/html.py md() returns for "## Goal / - build **the flow** / `x` / ``` y ``` / <script>… <img onerror>"
    first.body_html = "<h2>Goal</h2><ul><li>build <strong>the flow</strong></li></ul><p><code>x</code></p><pre><code>y</code></pre>"
      + "<p>&lt;script&gt;alert(1)&lt;/script&gt; &lt;img src=x onerror=alert(1)&gt;</p>";
    d.show_text = true;
    show(d);
    act(() => dialogs!.openInstructions(edgeId));
    const body = screen.getByTestId("flow-body");
    for (const tag of ["h2", "li", "strong", "code", "pre"]) expect(body.querySelector(tag)).not.toBeNull();
    expect(body.querySelector("script")).toBeNull();
    expect(body.querySelector("img")).toBeNull();
    expect(body.textContent).toContain("<script>alert(1)</script>");
  });

  it("picking another instruction updates the view and selects that event", () => {
    const d = fresh();
    const edgeId = d.edges.find((e) => instructions(d, e.id).length > 1)!.id;
    const second = instructions(d, edgeId)[1]!;
    show(d);
    act(() => dialogs!.openInstructions(edgeId));
    const items = within(screen.getByRole("list", { name: "Instructions on this link" })).getAllByRole("button");
    fireEvent.click(items[1]!);
    expect(items[1]!.getAttribute("aria-pressed")).toBe("true");
    expect(sel!.selection).toEqual({ kind: SelectionKind.Event, id: second.id });
  });

  it("Show on diagram and timeline closes the dialog and leaves the event selected", () => {
    const d = fresh();
    const edgeId = edgeOf(d);
    show(d);
    act(() => dialogs!.openInstructions(edgeId));
    fireEvent.click(screen.getByRole("button", { name: "Show on diagram and timeline" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(sel!.selection).toEqual({ kind: SelectionKind.Event, id: instructions(d, edgeId)[0]!.id });
  });

  it("hidden text shows the notice and no Markdown", () => {
    const d = fresh();
    d.show_text = false;
    show(d);
    act(() => dialogs!.openInstructions(edgeOf(d)));
    expect(screen.getByText(HIDDEN_TEXT)).toBeTruthy();
    expect(screen.queryByTestId("flow-body")).toBeNull();
  });

  it("Escape and Close close it, focus returns to the opener, and Tab stays inside", () => {
    show(fresh());
    const opener = screen.getByRole("button", { name: "opener" });
    opener.focus();
    fireEvent.click(opener);
    const dlg = screen.getByRole("dialog");
    const buttons = within(dlg).getAllByRole("button");
    buttons[buttons.length - 1]!.focus();
    fireEvent.keyDown(dlg, { key: "Tab" });
    expect(document.activeElement).toBe(buttons[0]);
    fireEvent.keyDown(dlg, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
    fireEvent.click(opener);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});

describe("findings and events dialogs", () => {
  it("findings dialog lists the node's findings and jumps to the target", () => {
    const d = fresh();
    const f = d.findings.find((x) => x.node)!;
    show(d);
    act(() => dialogs!.openFindings(f.node!));
    const dlg = screen.getByRole("dialog", { name: `Findings: ${label(d, f.node)}` });
    expect(within(dlg).getAllByRole("listitem")).toHaveLength(d.findings.filter((x) => x.node === f.node).length);
    fireEvent.click(within(dlg).getByRole("button", { name: f.text }));
    expect(sel!.selection).toEqual({ kind: f.target.kind, id: f.target.id });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("events dialog lists the node's events in time order and selects one", () => {
    const d = fresh();
    show(d);
    act(() => dialogs!.openEvents(NodeId.Coders));
    const dlg = screen.getByRole("dialog", { name: `${label(d, NodeId.Coders)}: messages and events` });
    const want = timeOrder(d.events.filter((e) => e.from_node === NodeId.Coders || e.to_node === NodeId.Coders));
    const rows = within(within(dlg).getByRole("list", { name: "Messages and events" })).getAllByRole("listitem");
    expect(rows).toHaveLength(want.length);
    expect(rows[0]!.textContent).toContain(want[0]!.title);
    // a row previews its event on the right and keeps the dialog open
    const last = want[want.length - 1]!;
    fireEvent.click(within(rows[rows.length - 1]!).getByRole("button"));
    expect(sel!.selection).toEqual({ kind: SelectionKind.Event, id: last.id });
    expect(within(dlg).getByRole("heading", { level: 3, name: last.title })).toBeTruthy();
    expect(within(dlg).getByRole("region", { name: "From" }).textContent).toContain(last.from ?? "unknown");
    // the jump back closes it
    fireEvent.click(within(dlg).getByRole("button", { name: "Show on diagram and timeline" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
