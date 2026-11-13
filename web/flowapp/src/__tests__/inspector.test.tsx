import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EdgeId, Lens, NodeId, Scope, SelectionKind, Severity } from "../constants";
import goalFixture from "../fixtures/goal.json";
import { fmtCost, fmtCount, fmtDuration, UNKNOWN } from "../format";
import { HIDDEN_TEXT, Inspector } from "../inspector/Inspector";
import { SummaryBar } from "../inspector/SummaryBar";
import { SelectionProvider, timeOrder, useSelection, type SelectionApi } from "../selection";
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
      <SummaryBar data={data} />
      <Inspector data={data} onOpenInstructions={onOpenInstructions} />
    </SelectionProvider>,
  );
  return onOpenInstructions;
}

const pick = (kind: SelectionKind, id: string) => act(() => api!.select({ kind, id }));

afterEach(() => {
  api = null;
});

describe("summary bar", () => {
  it("shows the totals", () => {
    const d = fresh();
    d.totals.cost = 21.39;
    d.totals.tokens = null;
    show(d);
    expect(document.querySelector('[data-kpi="Elapsed"]')!.textContent).toBe(fmtDuration(d.elapsed_s));
    expect(document.querySelector('[data-kpi="Agent time"]')!.textContent).toBe(fmtDuration(d.totals.agent_s));
    expect(document.querySelector('[data-kpi="Cost (est.)"]')!.textContent).toBe(fmtCost(21.39));
    expect(document.querySelector('[data-kpi="Tokens"]')!.textContent).toBe(UNKNOWN);
  });

  it("longest wait is the largest arrow wait, coloured by its severity", () => {
    const d = fresh();
    for (const e of d.edges) e.wait_s = null;
    Object.assign(d.edges[0]!, { wait_s: 60, severity: Severity.Ok });
    Object.assign(d.edges[1]!, { wait_s: 7200, severity: Severity.Bad });
    show(d);
    const kpi = document.querySelector('[data-kpi="Longest wait"]')!;
    expect(kpi.textContent).toBe(fmtDuration(7200));
    expect(kpi.className).toMatch(/fg_bad/);
  });

  it("findings render as chips and select their target", () => {
    const d = fresh();
    const f = d.findings[0]!;
    show(d);
    fireEvent.click(screen.getByRole("button", { name: f.text }));
    expect(api!.selection).toEqual({ kind: f.target.kind, id: f.target.id });
  });
});

describe("inspector", () => {
  it("with nothing selected ranks time then cost; the cost lens swaps them", () => {
    const d = fresh();
    d.nodes.find((n) => n.id === NodeId.Coders)!.cost = 3;
    d.nodes.find((n) => n.id === NodeId.Lead)!.cost = 5;
    show(d);
    const headings = () => screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings()).toEqual(["Where the time went", "Where the cost went"]);
    const values = [...document.querySelectorAll("[data-value]")].slice(0, 3).map((b) => Number(b.getAttribute("data-value")));
    expect(values).toEqual([...values].sort((a, b) => b - a));
    fireEvent.click(screen.getAllByRole("button", { name: /^Lead/ })[0]!);   // in both rankings
    expect(api!.selection).toEqual({ kind: SelectionKind.Node, id: NodeId.Lead });
    act(() => api!.clear());
    act(() => api!.setLens(Lens.Cost));
    expect(headings()).toEqual(["Where the cost went", "Where the time went"]);
  });

  it("selecting a box shows its figures, token breakdown and agents", () => {
    const d = fresh();
    const node = d.nodes.find((n) => n.agents.some((a) => a.task_id))!;
    node.tokens = { input: 120, output: 43042, cache_read: 5330357, cache_write: 139410 };
    show(d);
    pick(SelectionKind.Node, node.id);
    expect(screen.getByText("5,330,357")).toBeTruthy();
    for (const k of ["Input", "Output", "Cache read", "Cache write"]) expect(screen.getByText(k)).toBeTruthy();
    for (const a of node.agents) {
      const row = document.querySelector(`[data-agent="${a.name}"]`)!;
      expect(row.textContent).toContain(fmtDuration(a.work_s));
    }
    expect(d.scope).toBe(Scope.Goal);
    const withTask = node.agents.find((a) => a.task_id)!;
    const link = within(document.querySelector(`[data-agent="${withTask.name}"]`) as HTMLElement).getByRole("link", { name: "Open task flow" });
    expect(link.getAttribute("href")).toBe(`/task/${withTask.task_id}`);
    expect(fmtCount(43042)).toBe("43,042");
  });

  it("selecting an arrow shows its wait and View instructions (n)", () => {
    const d = fresh();
    const withIns = d.edges.find((e) => d.events.some((x) => x.edge === e.id && x.is_instruction))!;
    const n = d.events.filter((x) => x.edge === withIns.id && x.is_instruction).length;
    const onOpen = show(d);
    pick(SelectionKind.Edge, withIns.id);
    fireEvent.click(screen.getByRole("button", { name: `View instructions (${n})` }));
    expect(onOpen).toHaveBeenCalledWith(withIns.id);
    const without = d.edges.find((e) => !d.events.some((x) => x.edge === e.id && x.is_instruction))!;
    pick(SelectionKind.Edge, without.id);
    expect(screen.queryByRole("button", { name: /View instructions/ })).toBeNull();
    pick(SelectionKind.Edge, EdgeId.PmCoders);
    expect(screen.getAllByText(fmtDuration(d.edges.find((e) => e.id === EdgeId.PmCoders)!.wait_s)).some((el) => el.tagName === "DD" && !el.hasAttribute("data-kpi"))).toBe(true);
  });

  it("selecting an event shows the route, step cost and the body or the hidden-text notice", () => {
    const d = fresh();
    const ev = d.events.find((e) => e.body_html)!;
    ev.cost = 0.98;
    show(d);
    pick(SelectionKind.Event, ev.id);
    expect(screen.getByText(`${ev.from} to ${ev.to}`)).toBeTruthy();
    expect(screen.getByText(fmtCost(0.98))).toBeTruthy();
    expect(screen.getByTestId("flow-body").innerHTML).toBe(ev.body_html);
  });

  it("with text off the body area shows the notice", () => {
    const d = fresh();
    d.show_text = false;
    d.events.forEach((e) => (e.body_html = null));
    show(d);
    pick(SelectionKind.Event, d.events[0]!.id);
    expect(screen.getByText(HIDDEN_TEXT)).toBeTruthy();
  });

  it("cost marked not exact shows a note", () => {
    const d = fresh();
    const ev = d.events[0]!;
    ev.cost_exact = false;
    ev.cost_note = "no session log found for coder-x";
    show(d);
    pick(SelectionKind.Event, ev.id);
    expect(screen.getByTestId("flow-cost-note").textContent).toBe(ev.cost_note);
  });

  it("event list rows select events and Around this event shows two before and two after", () => {
    const d = fresh();
    const ordered = timeOrder(d.events);
    const mid = ordered[5]!;
    show(d);
    pick(SelectionKind.Event, mid.id);
    const around = screen.getByRole("heading", { name: "Around this event" }).parentElement!;
    const rows = within(around).getAllByRole("button");
    expect(rows).toHaveLength(4);
    fireEvent.click(rows[3]!);
    expect(api!.selection).toEqual({ kind: SelectionKind.Event, id: ordered[7]!.id });
  });
});
