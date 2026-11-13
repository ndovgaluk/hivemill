import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, LOAD_FAILED } from "../App";
import { EventKind, LaneId, Scope, SelectionKind } from "../constants";
import goalFixture from "../fixtures/goal.json";
import type { FlowData, FlowEvent } from "../types";

const H = { hidden: true } as const;
const fresh = () => structuredClone(goalFixture) as unknown as FlowData;

function serve(...bodies: { status?: number; body: unknown }[]) {
  let i = 0;
  const fetchMock = vi.fn(async () => {
    const b = bodies[Math.min(i++, bodies.length - 1)]!;
    return new Response(typeof b.body === "string" ? b.body : JSON.stringify(b.body), { status: b.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function mount(data: FlowData, pollMs?: number) {
  render(<App target={{ scope: Scope.Goal, id: data.id }} pollMs={pollMs} />);
  await screen.findByRole("region", { name: "Diagram" });
  // React Flow renders the boxes after its first measure, a tick after the region: wait for them too
  await screen.findByTestId(`flow-node-${data.nodes[0]!.id}`);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("app", () => {
  it("diagram and timeline follow one selection", async () => {
    const d = fresh();
    serve({ body: d });
    await mount(d);
    fireEvent.click(within(screen.getByRole("region", { name: "Diagram" })).getByRole("button", { name: "Coders", ...H }));
    expect(screen.getByTestId(`flow-lane-${LaneId.Coders}`).getAttribute("data-hot")).toBe("true");
    const verdict = d.events.find((e) => e.kind === EventKind.Verdict && e.edge && e.lane)!;
    const mark = within(screen.getByTestId(`flow-lane-${verdict.lane}`)).getAllByRole("button")
      .find((b) => b.getAttribute("data-mark") === verdict.id)!;
    fireEvent.click(mark);
    expect(screen.getByTestId(`flow-edge-${verdict.edge}`).getAttribute("data-flow")).not.toBeNull();
    expect(within(screen.getByRole("complementary", { name: "Inspector" })).getByRole("heading", { level: 2 }).textContent)
      .toBe(verdict.title);
  });

  it("clicking an arrow opens its instructions", async () => {
    const d = fresh();
    serve({ body: d });
    await mount(d);
    const edge = d.edges.find((e) => d.events.some((x) => x.edge === e.id && x.is_instruction))!;
    fireEvent.click(await screen.findByTestId(`flow-edge-${edge.id}`));   // the arrow layer mounts in React Flow's viewport portal
    const dlg = screen.getByRole("dialog", { name: /^Instructions: / });
    expect(within(dlg).getByRole("region", { name: "From" })).toBeTruthy();
    expect(within(dlg).getByRole("region", { name: "To" })).toBeTruthy();
  });

  it("refresh keeps the selection and shows the new total", async () => {
    const d = fresh();
    const more = fresh();
    const extra: FlowEvent = { ...more.events[more.events.length - 1]!, id: "M999999", key: "M999999", t_s: (more.elapsed_s ?? 0) + 60 };
    more.events.push(extra);
    serve({ body: d }, { body: more });
    await mount(d, 200);
    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    // the extra event comes last in time, so the first event keeps position 1 while the total grows
    await waitFor(() => expect(screen.getByTestId("flow-position").textContent).toBe(`1 / ${more.events.length}`), { timeout: 3000 });
    expect(screen.getByTestId("flow-diagram-ref").getAttribute("data-ref")).toBe(
      [...d.events].sort((a, b) => (a.t_s ?? Infinity) - (b.t_s ?? Infinity))[0]!.id);
  });

  it("goal to task drill-down", async () => {
    const d = fresh();
    serve({ body: d });
    await mount(d);
    const node = d.nodes.find((n) => n.agents.some((a) => a.task_id))!;
    fireEvent.click(within(screen.getByRole("region", { name: "Diagram" })).getByRole("button", { name: node.label, ...H }));
    const a = node.agents.find((x) => x.task_id)!;
    const links = screen.getAllByRole("link", { name: "Open task flow" });
    expect(links.map((l) => l.getAttribute("href"))).toContain(`/task/${a.task_id}`);
    expect(SelectionKind.Node).toBeTruthy();
  });

  it("error state offers Retry", async () => {
    const d = fresh();
    const fetchMock = serve({ status: 404, body: { error: "not found" } }, { body: d });
    render(<App target={{ scope: Scope.Goal, id: d.id }} />);
    expect((await screen.findByRole("alert")).textContent).toContain(LOAD_FAILED);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("region", { name: "Diagram" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
