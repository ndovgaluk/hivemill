import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dir, EdgeId, FindingTarget, NodeId, NodeState, SelectionKind, Severity } from "../constants";
import { MSGS_ONLY, NO_SESSIONS, WAITED_TOTAL } from "../diagram/BoxNode";
import { Diagram, type DiagramHandlers } from "../diagram/Diagram";
import goalFixture from "../fixtures/goal.json";
import { fmtCost, fmtDuration, UNKNOWN } from "../format";
import { SelectionProvider, useSelection, type SelectionApi } from "../selection";
import type { FlowData } from "../types";

// React Flow keeps unmeasured nodes visibility:hidden in jsdom: role queries include hidden elements
const H = { hidden: true } as const;
const fresh = () => structuredClone(goalFixture) as unknown as FlowData;

let api: SelectionApi | null = null;
function Probe() {
  api = useSelection();
  return null;
}

function show(data: FlowData, handlers: DiagramHandlers = {}) {
  return render(
    <SelectionProvider data={data}>
      <Probe />
      <Diagram data={data} {...handlers} />
    </SelectionProvider>,
  );
}

const node = (id: string) => screen.getByTestId(`flow-node-${id}`);

afterEach(() => {
  api = null;
  vi.restoreAllMocks();
});

describe("diagram", () => {
  it("renders one box per node with name, work time and cost", () => {
    const data = fresh();
    const coders = data.nodes.find((n) => n.id === NodeId.Coders)!;
    coders.cost = 1.25;
    const unknown = data.nodes.find((n) => n.id === NodeId.Lead)!;   // has a session, figures not known
    unknown.work_s = null;
    show(data);
    for (const n of data.nodes) expect(node(n.id)).toBeTruthy();
    const box = screen.getByRole("button", { name: coders.label, ...H });
    expect(box.textContent).toContain(fmtDuration(coders.work_s));
    expect(box.textContent).toContain(fmtCost(1.25));
    expect(node(unknown.id).textContent).toContain(UNKNOWN);
    expect(node(unknown.id).textContent).not.toContain("0s");
  });

  it("a box with no sessions says so instead of unknown figures", () => {
    const data = fresh();
    for (const id of [NodeId.Boss, NodeId.Gate]) Object.assign(data.nodes.find((n) => n.id === id)!, { agents: [], work_s: null, cost: null });
    show(data);
    expect(node(NodeId.Boss).textContent).toContain(MSGS_ONLY);
    expect(node(NodeId.Gate).textContent).toContain(NO_SESSIONS);
    expect(node(NodeId.Boss).textContent).not.toContain(UNKNOWN);
  });

  it("renders one label per edge with the wait", () => {
    const data = fresh();
    const pc = data.edges.find((e) => e.id === EdgeId.PmCoders)!;
    pc.wait_s = 7380;
    pc.severity = Severity.Bad;
    show(data);
    for (const e of data.edges) expect(screen.getByTestId(`flow-edge-${e.id}`)).toBeTruthy();
    const chip = screen.getByTestId(`flow-edge-${EdgeId.PmCoders}`);
    expect(chip.textContent).toBe(fmtDuration(7380));
    expect(chip.getAttribute("data-severity")).toBe(Severity.Bad);
  });

  it("clicking a box selects it and dims the others", () => {
    show(fresh());
    const box = screen.getByRole("button", { name: "Coders", ...H });
    fireEvent.click(box);
    expect(box.getAttribute("aria-pressed")).toBe("true");
    expect(node(NodeId.Boss).getAttribute("data-dim")).toBe("true");
    fireEvent.click(box);
    expect(box.getAttribute("aria-pressed")).toBe("false");
    expect(node(NodeId.Boss).getAttribute("data-dim")).toBe("false");
  });

  it("selecting an event animates its edge in the event's direction", () => {
    const data = fresh();
    const ev = data.events.find((e) => e.dir === Dir.Back && e.edge && e.edge !== EdgeId.Bus && e.from_node)
      ?? data.events.find((e) => e.dir === Dir.Back && e.from_node)!;
    show(data);
    act(() => api!.select({ kind: SelectionKind.Event, id: ev.id }));
    expect(screen.getByTestId(`flow-edge-${ev.edge}`).getAttribute("data-flow")).toBe("reverse");
    expect(node(ev.from_node!).getAttribute("data-pulse")).toBe("true");
  });

  it("cost lens swaps the main number and marks the most expensive box", () => {
    const data = fresh();
    data.nodes.find((n) => n.id === NodeId.Coders)!.cost = 1.5;
    data.nodes.find((n) => n.id === NodeId.Gate)!.cost = 2.5;
    show(data);
    fireEvent.click(screen.getByRole("button", { name: "Cost" }));
    const gate = node(NodeId.Gate);
    expect(gate.querySelector('[data-value="main"]')?.textContent).toBe(fmtCost(2.5));
    expect(gate.querySelector('[data-value="second"]')?.textContent).toBe(
      fmtDuration(data.nodes.find((n) => n.id === NodeId.Gate)!.work_s));
    expect(document.querySelectorAll('[data-top="true"]')).toHaveLength(1);
    expect(gate.getAttribute("data-top")).toBe("true");
  });

  it("badge shows the finding count and opens the findings list", () => {
    const data = fresh();
    const f = { severity: Severity.Warn, text: "x", target: { kind: FindingTarget.Node, id: NodeId.Gate }, node: NodeId.Gate };
    data.findings = [f, { ...f, severity: Severity.Bad }];
    const onOpenFindings = vi.fn();
    show(data, { onOpenFindings });
    fireEvent.click(screen.getByRole("button", { name: "2 findings on Review gate", ...H }));
    expect(onOpenFindings).toHaveBeenCalledWith(NodeId.Gate);
  });

  it("node toolbar appears for the selected box", () => {
    const onExpandLanes = vi.fn();
    const onOpenEvents = vi.fn();
    show(fresh(), { onExpandLanes, onOpenEvents });
    expect(screen.queryByRole("button", { name: "Expand on timeline", ...H })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Lead", ...H }));
    fireEvent.click(screen.getByRole("button", { name: "Expand on timeline", ...H }));
    fireEvent.click(screen.getByRole("button", { name: "Messages and events", ...H }));
    expect(onExpandLanes).toHaveBeenCalledWith(NodeId.Lead);
    expect(onOpenEvents).toHaveBeenCalledWith(NodeId.Lead);
  });

  it("zoom buttons change the zoom label between the allowed steps and Fit resets it", () => {
    show(fresh());
    const label = screen.getByTestId("flow-zoom");
    expect(label.textContent).toBe("100%");
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(label.textContent).toBe("125%");
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(label.textContent).toBe("75%");
    fireEvent.click(screen.getByRole("button", { name: "Fit" }));
    expect(label.textContent).toBe("100%");
  });

  it("a plain wheel leaves the page to scroll; only a ctrl wheel is taken for zoom (HM-6)", () => {
    show(fresh());
    const pane = document.querySelector(".react-flow__pane") ?? document.querySelector(".react-flow")!;
    const plain = new WheelEvent("wheel", { deltaY: -100, bubbles: true, cancelable: true });
    pane.dispatchEvent(plain);
    expect(plain.defaultPrevented).toBe(false);
    const ctrl = new WheelEvent("wheel", { deltaY: -100, ctrlKey: true, bubbles: true, cancelable: true });
    pane.dispatchEvent(ctrl);
    expect(ctrl.defaultPrevented).toBe(true);
  });

  it("clicking an edge label with instructions selects it and opens the viewer", () => {
    const data = fresh();
    const ev = data.events.find((e) => e.is_instruction && e.edge)!;
    const onOpenInstructions = vi.fn();
    show(data, { onOpenInstructions });
    fireEvent.click(screen.getByTestId(`flow-edge-${ev.edge}`));
    expect(onOpenInstructions).toHaveBeenCalledWith(ev.edge);
    expect(api!.selection).toEqual({ kind: SelectionKind.Edge, id: ev.edge });
  });

  it("reduced motion turns animation off", () => {
    vi.spyOn(window, "matchMedia").mockImplementation((q: string) =>
      ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList);
    const data = fresh();
    const ev = data.events.find((e) => e.edge && e.from_node)!;
    const { container } = show(data);
    act(() => api!.select({ kind: SelectionKind.Event, id: ev.id }));
    expect(container.querySelector('[class*="animated"]')).toBeNull();
  });

  it("the box working now pulses and shows a turning cog, also with reduced motion; a selected or idle box does not pulse", () => {
    const data = fresh();
    for (const n of data.nodes) n.state = n.id === NodeId.Coders ? NodeState.Live : NodeState.Done;
    const button = () => screen.getByRole("button", { name: data.nodes.find((n) => n.id === NodeId.Coders)!.label, ...H });
    const cog = () => screen.getByTestId(`flow-node-working-${NodeId.Coders}`);
    const first = show(data);
    expect(button().className).toMatch(/liveBox/);
    expect(first.container.querySelectorAll('[class*="liveBox"]')).toHaveLength(1);
    expect(cog().getAttribute("class")).toMatch(/spin/);
    expect(first.container.querySelectorAll('[data-testid^="flow-node-working-"]')).toHaveLength(1);
    first.unmount();
    vi.spyOn(window, "matchMedia").mockImplementation((q: string) =>
      ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList);
    show(data);
    expect(button().className).toMatch(/liveBox/);   // the owner's choice: "working now" shows also with reduced motion
    expect(cog().getAttribute("class")).toMatch(/spin/);
    act(() => api!.select({ kind: SelectionKind.Node, id: NodeId.Coders }));
    expect(button().className).not.toMatch(/liveBox/);   // a selected box shows the selection instead
    expect(cog()).toBeTruthy();
  });

  it("the Waiting box shows how long, what for, and a link to the PR that opens in a new tab", () => {
    const data = fresh();
    const url = "https://github.com/example/repo/pull/7";
    const wait = data.nodes.find((n) => n.id === NodeId.Wait)!;
    Object.assign(wait, { state: NodeState.Live, work_s: 4000, current_s: 600, note: "PR checks, then review: T-1", links: [{ label: "PR T-1", url }] });
    show(data);
    const box = node(NodeId.Wait);
    expect(box.textContent).toContain(fmtDuration(600));
    expect(box.textContent).toContain("PR checks, then review: T-1");
    const a = box.querySelector("a")!;
    expect([a.getAttribute("href"), a.getAttribute("target"), a.getAttribute("rel")]).toEqual([url, "_blank", "noopener noreferrer"]);
    expect(box.querySelector("button a")).toBeNull();
    expect(box.querySelector("button")!.getAttribute("title")).toContain(`${fmtDuration(4000)} ${WAITED_TOTAL}`);
  });

  it("a node the bundle has no position for is left out, the rest still render", () => {
    const data = fresh();
    data.nodes.push({ ...data.nodes[0]!, id: "from-a-newer-server" as NodeId, label: "Newer" });
    show(data);
    expect(screen.queryByTestId("flow-node-from-a-newer-server")).toBeNull();
    expect(node(NodeId.Coders)).toBeTruthy();
  });

  it("the selected arrow, its label and the selected box glow", () => {
    const data = fresh();
    const { container } = show(data);
    act(() => api!.select({ kind: SelectionKind.Edge, id: EdgeId.Rework }));
    const path = screen.getByTestId(`flow-edge-path-${EdgeId.Rework}`);
    expect(path.getAttribute("data-picked")).toBe("true");
    expect(path.getAttribute("class")).toMatch(/glow/);
    expect(screen.getByTestId(`flow-edge-${EdgeId.Rework}`).className).toMatch(/glowBox/);
    expect(container.querySelectorAll('path[data-picked="true"]')).toHaveLength(1);
    act(() => api!.select({ kind: SelectionKind.Node, id: NodeId.Coders }));
    expect(screen.getByRole("button", { name: data.nodes.find((n) => n.id === NodeId.Coders)!.label, ...H }).className).toMatch(/glowBox/);
  });

  it("arrows end in a head of their severity colour; two-way arrows have a head at both ends", () => {
    const data = fresh();
    const oneWay = data.edges.find((e) => e.id === EdgeId.Rework)!;
    Object.assign(oneWay, { severity: Severity.Bad, counts: { forward: 3, back: 0 } });
    const twoWay = data.edges.find((e) => e.id === EdgeId.BossDirector)!;
    Object.assign(twoWay, { severity: Severity.Ok, counts: { forward: 2, back: 7 } });
    const { container } = show(data);
    const headOf = (ref: string | null) => container.querySelector(ref!.slice(4, -1))?.getAttribute("data-head");
    const rw = screen.getByTestId(`flow-edge-path-${EdgeId.Rework}`);
    expect(headOf(rw.getAttribute("marker-end"))).toBe(Severity.Bad);
    expect(rw.getAttribute("marker-start")).toBeNull();
    const bd = screen.getByTestId(`flow-edge-path-${EdgeId.BossDirector}`);
    expect(headOf(bd.getAttribute("marker-end"))).toBe(Severity.Ok);
    expect(headOf(bd.getAttribute("marker-start"))).toBe(Severity.Ok);
  });

  it("with reduced motion the selected arrow is marked but does not animate", () => {
    vi.spyOn(window, "matchMedia").mockImplementation((q: string) =>
      ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList);
    show(fresh());
    act(() => api!.select({ kind: SelectionKind.Edge, id: EdgeId.Rework }));
    const path = screen.getByTestId(`flow-edge-path-${EdgeId.Rework}`);
    expect(path.getAttribute("data-picked")).toBe("true");
    expect(path.getAttribute("class")).not.toMatch(/glow/);
  });
});
