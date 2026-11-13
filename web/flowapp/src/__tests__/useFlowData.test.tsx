import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { MountAttr, Region, Scope } from "../constants";
import goal from "../fixtures/goal.json";
import { readTarget } from "../useFlowData";

const GOAL_ID = "G-1";

function mount(scope: string, id: string) {
  const el = document.createElement("div");
  el.setAttribute(MountAttr.Scope, scope);
  el.setAttribute(MountAttr.Id, id);
  return el;
}

function respond(body: string, status = 200) {
  const fetchMock = vi.fn(async () => new Response(body, { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useFlowData", () => {
  it("loads the payload for the scope and id in the mount element", async () => {
    const fetchMock = respond(JSON.stringify(goal));
    const { container } = render(<App target={readTarget(mount(Scope.Goal, GOAL_ID), MountAttr.Scope, MountAttr.Id)} />);
    await waitFor(() => expect(container.querySelector(`[data-region="${Region.Diagram}"]`)).not.toBeNull());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe(`/api/flow/${Scope.Goal}/${GOAL_ID}.json`);
    for (const region of Object.values(Region)) {
      expect(container.querySelector(`[data-region="${region}"]`)).not.toBeNull();
    }
  });

  it("shows an error state on 404 and on invalid JSON", async () => {
    respond(JSON.stringify({ error: "not found" }), 404);
    const first = render(<App target={{ scope: Scope.Task, id: "T-404" }} />);
    expect((await screen.findByRole("alert")).textContent).toContain("HTTP 404");
    first.unmount();
    respond("{not json");
    render(<App target={{ scope: Scope.Task, id: "T-1" }} />);
    expect((await screen.findByRole("alert")).textContent).toContain("invalid JSON");
  });

  it("rejects a mount element without a valid scope", () => {
    expect(readTarget(mount("plan", GOAL_ID), MountAttr.Scope, MountAttr.Id)).toBeNull();
    expect(readTarget(null, MountAttr.Scope, MountAttr.Id)).toBeNull();
  });
});
