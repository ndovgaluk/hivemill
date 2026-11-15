// HM-50 (HM-69, HM-70): each workflow's diagram from the payload's own layout, planned steps dashed, the workflow line,
// the children, and the engine's incidents on the timeline. Fixtures are written by web/flow.py build() on the HM-50
// Python test seed, so they match the server.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EdgeId, NodeId } from "../constants";
import { PLANNED } from "../diagram/BoxNode";
import { Diagram } from "../diagram/Diagram";
import { OLD_WORKFLOW, workflowText } from "../diagram/Workflow";
import goalFixture from "../fixtures/goal.json";
import hugeNone from "../fixtures/engine-huge-none.json";
import simpleGithub from "../fixtures/engine-simple-github.json";
import { SelectionProvider } from "../selection";
import { INCIDENT } from "../timeline/QuickInfo";
import { Timeline } from "../timeline/Timeline";
import type { FlowData } from "../types";

const load = (f: unknown) => structuredClone(f) as FlowData;
const node = (id: string) => screen.queryByTestId(`flow-node-${id}`);

function show(data: FlowData) {
  return render(
    <SelectionProvider data={data}>
      <Diagram data={data} />
    </SelectionProvider>,
  );
}

describe("workflow diagrams (HM-50)", () => {
  it("huge with CI none: planned steps dashed with their note, land says no tests, no old boxes", () => {
    show(load(hugeNone));
    for (const id of [NodeId.Architect, NodeId.BranchQa, NodeId.MergeQueue]) {
      expect(node(id)!.dataset.planned).toBe("true");
      expect(node(id)!.textContent).toContain(PLANNED);
      expect((within(node(id)!).getByRole("button", { hidden: true }) as HTMLButtonElement).disabled).toBe(true);
    }
    expect(node(NodeId.Land)!.textContent).toContain("no tests");
    expect(node(NodeId.Builder)!.dataset.planned).toBe("false");
    for (const id of [NodeId.Judge, NodeId.Lead, NodeId.Coders, NodeId.Pm]) expect(node(id)).toBeNull();
    expect(screen.getByTestId(`flow-edge-path-${EdgeId.NonConvergence}`).dataset.planned).toBe("true");
    expect(screen.getByTestId(`flow-edge-path-${EdgeId.BuildReview}`).dataset.planned).toBe("false");
  });

  it("simple with CI github: pull request, review gate, judge and merged after the reviewer", () => {
    show(load(simpleGithub));
    for (const id of [NodeId.Pr, NodeId.Reviewer, NodeId.Qa, NodeId.Judge, NodeId.Main, NodeId.Done]) expect(node(id)).not.toBeNull();
    expect(screen.queryByTestId(`flow-group-${NodeId.Gate}`)).not.toBeNull();
    expect(node(NodeId.Architect)).toBeNull();
  });

  it("boxes sit where the payload's layout puts them", () => {
    const d = load(hugeNone);
    show(d);
    const at = d.layout!.boxes[NodeId.MergeQueue]!;
    const wrapper = node(NodeId.MergeQueue)!.closest(".react-flow__node") as HTMLElement;
    expect(wrapper.style.transform).toContain(`${at.x}px`);
  });

  it("the header names the workflow, how it was picked and the CI mode", () => {
    show(load(hugeNone));
    expect(screen.getByTestId("flow-workflow").textContent).toBe("Workflow: huge (chosen) · CI none: no PR, no tests · run building");
    expect(workflowText(load(goalFixture))).toBe(OLD_WORKFLOW);
  });

  it("lists each child with its state and fix rounds", () => {
    show(load(hugeNone));
    expect(screen.getByTestId("flow-child-HM-2").textContent).toBe("HM-2 reviewed · 1 fix round");
    expect(screen.getByTestId("flow-child-HM-3").textContent).toBe("HM-3 fixing · 2 fix rounds");
  });

  it("the old workflow keeps its fixed layout and shows no children", () => {
    show(load(goalFixture));
    expect(node(NodeId.Coders)).not.toBeNull();
    expect(screen.queryByRole("region", { name: "Children" })).toBeNull();
  });
});

describe("engine incidents on the timeline (HM-70)", () => {
  it("each incident is a mark whose quick info gives kind, cause and the full reason", () => {
    const d = load(hugeNone);
    render(
      <SelectionProvider data={d}>
        <Timeline data={d} onOpenInstructions={() => {}} />
      </SelectionProvider>,
    );
    const marks = d.events.filter((e) => e.incident);
    expect(marks.map((e) => [e.lane, e.incident!.cause])).toEqual([
      [NodeId.ChildReview, "review-changes"], [NodeId.Engine, "land-refused"]]);
    for (const e of marks) {
      fireEvent.click(document.querySelector(`[data-mark="${e.id}"]`)!);
      const info = screen.getByTestId("flow-quick-incident");
      expect(info.textContent).toContain(`${INCIDENT}: ${e.incident!.kind} · ${e.incident!.cause}`);
      expect(info.textContent).toContain(e.incident!.summary);
    }
  });
});

describe("fit to width (HM-50)", () => {
  it("Fit zooms a wide diagram so its whole width fits the canvas; a narrow one stays at 100 %", () => {
    const width = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 1224 });
    try {
      const wide = load(hugeNone);
      wide.layout!.canvas.w = 2400;   // as huge with CI github: wider than the canvas
      const { unmount } = show(wide);
      fireEvent.click(screen.getByRole("button", { name: "Fit" }));
      expect(screen.getByTestId("flow-zoom").textContent).toBe("50%");   // (1224 − 24) / 2400
      fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
      expect(screen.getByTestId("flow-zoom").textContent).toBe("75%");   // the next step up from the fitted zoom
      unmount();
      const narrow = load(hugeNone);
      narrow.layout!.canvas.w = 1000;   // as simple with CI none: fits at 100 %, never zoomed in past it
      show(narrow);
      fireEvent.click(screen.getByRole("button", { name: "Fit" }));
      expect(screen.getByTestId("flow-zoom").textContent).toBe("100%");
    } finally {
      if (width) Object.defineProperty(HTMLElement.prototype, "clientWidth", width);
    }
  });
});
