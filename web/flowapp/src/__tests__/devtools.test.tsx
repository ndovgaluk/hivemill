import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AGENTATION_ENDPOINT, AgentationMode, DevEnv, DevParam, FIXTURE_ID, MountAttr, Scope } from "../constants";
import { applyAddress } from "../dev/address";
import { toolbarProps } from "../dev/toolbar";

const MARKER = "agentation-marker";
const loads = vi.hoisted(() => ({ count: 0 }));

vi.mock("agentation", () => {
  loads.count += 1;
  return { Agentation: (p: { endpoint?: string }) => <div data-testid={MARKER} data-endpoint={p.endpoint ?? ""} /> };
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function devTools(dev: boolean) {
  vi.stubEnv("DEV", dev);
  vi.resetModules();
  return (await import("../dev/DevTools")).DevTools;
}

describe("dev tools", () => {
  it("toolbar renders only in development", async () => {
    const On = await devTools(true);
    const on = render(<On />);
    expect(await screen.findByTestId(MARKER)).toBeTruthy();
    on.unmount();
    const before = loads.count;
    const Off = await devTools(false);
    const { container } = render(<Off />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container.innerHTML).toBe("");
    expect(screen.queryByTestId(MARKER)).toBeNull();
    expect(loads.count).toBe(before);   // the agentation module was not imported again
  });

  it("endpoint comes from the constant or the env override", () => {
    expect(toolbarProps({})).toEqual({ endpoint: AGENTATION_ENDPOINT });
    expect(toolbarProps({ [DevEnv.AgentationEndpoint]: "http://localhost:4800" })).toEqual({ endpoint: "http://localhost:4800" });
    expect(toolbarProps({ [DevEnv.AgentationMode]: AgentationMode.Copy })).toEqual({});
  });

  it("dev mount reads scope and id from the address", () => {
    const el = document.createElement("div");
    expect(applyAddress(el, `?${DevParam.Scope}=${Scope.Task}&${DevParam.Id}=T-0003`)).toBe(true);
    expect(el.getAttribute(MountAttr.Scope)).toBe(Scope.Task);
    expect(el.getAttribute(MountAttr.Id)).toBe("T-0003");

    const fx = document.createElement("div");
    expect(applyAddress(fx, `?${DevParam.Fixture}=${Scope.Goal}`)).toBe(true);
    expect(fx.getAttribute(MountAttr.Id)).toBe(FIXTURE_ID);

    const none = document.createElement("div");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(applyAddress(none, "")).toBe(false);
    expect(none.querySelector("form")).not.toBeNull();
    expect(none.hasAttribute(MountAttr.Scope)).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
